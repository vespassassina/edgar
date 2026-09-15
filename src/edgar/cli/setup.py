"""What `-p` and the REPL share: config, tools, the permission guard, the verify
check, the prompt's prefix, the runtime built from them, and opening and closing
a session."""

# A session's life, as the REPL and -p both run it:
#
#   prepare   the working directory and layered config; yolo only with a human's say-so
#   setup     once per session: the permission guard, skills, tools and the MCP
#             servers (configured, none started), the verify
#             check, the prompt's prefix (personality, instruction files, pinned
#             facts, skill index) and startup warnings
#   runtime   the provider for the chosen model, and the Runtime the loop runs on;
#             built again by /model, which keeps everything setup made
#   begin     a new session on disk, or one replayed from its JSONL (--resume);
#             every turn's cost is added to today's spend from then on
#   daily     before each turn: what is left of daily_cost_cap becomes its turn cap
#   finish    note control files that changed while it ran, for the next session

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from edgar.agents.discovery import discover as discover_agents
from edgar.agents.spawn import subagents_config
from edgar.cli.trust import from_project
from edgar.config.load import load, project_config
from edgar.config.schema import Config, McpSection
from edgar.context.builder import PERSONALITY_WARN, Section, notes, pinned, skill_index, system_text
from edgar.context.prompts import choose_profile, load_prompt, profile_prompt
from edgar.context.tokens import approx_tokens
from edgar.core.errors import BudgetExceeded, ConfigError, PermissionDenied, UsageError
from edgar.core.events import Event, EventBus, ModelSelected, TurnFinished
from edgar.core.loop import Runtime
from edgar.core.session import Session
from edgar.core.verify import Check
from edgar.memory.retriever import retriever
from edgar.memory.store import Memory, project_scope
from edgar.permissions.control import control_files, snapshot
from edgar.permissions.guard import Asker, Guard
from edgar.permissions.policy import Deny, Policy
from edgar.providers.fallback import chain_from_config
from edgar.providers.registry import resolve, split
from edgar.providers.routing import RoutingContext, Selection, routes_from_config, select_model
from edgar.skills.discovery import Found, discover
from edgar.storage.db import Store
from edgar.storage.transcript import control_changes, find, replay, start
from edgar.tools.base import Tool
from edgar.tools.builtin.memory_tools import Recall, Remember
from edgar.tools.builtin.shell import Shell
from edgar.tools.builtin.skill import SkillTool
from edgar.tools.builtin.task import TaskTool
from edgar.tools.builtin.tool_search import searchable
from edgar.tools.mcp.client import Server, servers
from edgar.tools.registry import ToolRegistry, registry_for


def prepare(
    cwd: Path | None,
    *,
    model: str | None,
    mode: str | None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    confirm_yolo: Callable[[], bool] | None = None,
) -> tuple[Path, Config]:
    root = (cwd or Path.cwd()).resolve()
    if not root.is_dir():
        raise UsageError(f"--cwd {root} is not a directory")
    flags = {}
    if mode is not None:
        flags["permissions.mode"] = (mode, "flag --mode")
    if model is not None:
        flags["model.default"] = (model, "flag --model")
    config = load(root, home=home, env=env, flags=flags)
    if config.permissions.mode == "yolo":
        _allow_yolo(config, os.environ if env is None else env, confirm_yolo)
    return root, config


def _allow_yolo(config: Config, env: Mapping[str, str], confirm: Callable[[], bool] | None) -> None:
    """yolo turns every check off, so config alone never reaches it: a file can be
    committed, shared, or written by a tool [PERM-9]."""
    if env.get("EDGAR_YOLO") == "1":
        return
    if config.origins["permissions.mode"] == "flag --mode" and confirm is not None and confirm():
        return
    raise ConfigError(
        "yolo mode needs EDGAR_YOLO=1, or --mode yolo and a typed confirmation",
        hint="yolo turns off every permission check; config alone never enables it",
    )


@dataclass
class Setup:
    """Per session, and unchanged by `/model`: grants given stay given."""

    root: Path
    config: Config
    home: Path
    env: Mapping[str, str] | None
    tools: ToolRegistry
    guard: Guard
    check: Check | None
    pinned: list[Section]  # personality and instruction files, read once [CFG-8]
    control: dict[str, str]  # control-file digests when the session began [PERM-12]
    warnings: list[str]
    memory: Memory
    scope: str  # the project's memory scope
    servers: list[Server]  # the MCP servers this session may use; none is running [TOOL-8]
    browser: Server | None  # what /browser would start, if [browser] names a server


def setup(
    root: Path,
    config: Config,
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    verify: str | None = None,
    project_exec: bool = True,
    asker: Asker | None = None,
) -> Setup:
    home = home or Path.home()
    p = config.permissions
    base = Policy(
        mode=p.mode,
        cwd=root,
        home=home.resolve(),
        rules=p.tools,
        write_paths=tuple(p.write_paths),
        shell_allow=tuple(p.shell_allow),
        shell_deny=tuple(p.shell_deny),
        control=control_files(root, home, config.instructions.files),
    )
    guard = Guard(base, asker=asker, store=Store(root / ".edgar" / "edgar.db"))
    tools, found, servers_here = toolset(root, home, config, project_exec=project_exec)
    agents = discover_agents(root, home)
    if agents.agents:
        limits = subagents_config(config.later)
        tools.add([TaskTool(agents.agents, tools, guard, config, env, limits)])
    skills = list(found.skills.values())
    from_project = config.origins.get("verify.command") == str(project_config(root))
    command = verify or (config.verify.command if project_exec or not from_project else None)
    check = Check(command, config.verify.max_attempts, config.shell.program) if command else None
    files = config.instructions.files
    # The pinned facts are chosen now and frozen: a fact saved mid-session is found by
    # `recall`, and pinned from the next session on [MEM-6].
    memory, scope = open_memory(home, config), project_scope(root)
    facts = [f.text for f in memory.pinned(scope, config.memory.pinned_max)]
    kept = notes(facts, config.memory.pinned_max, memory.path)
    sections = pinned(root, home, files) + kept + skill_index(skills, root)
    warnings = [
        *tools.warnings,
        *found.warnings,
        *found.problems,
        *agents.warnings,
        *agents.problems,
    ]
    for sec in sections:
        if sec.name == "personality" and approx_tokens(sec.text) > PERSONALITY_WARN:
            warnings.append(f"{sec.source} is ~{approx_tokens(sec.text):,} tokens; keep it short")
    last, changed = control_changes(root)
    if changed:
        listed = ", ".join(changed)
        warnings.append(f"control files changed during session {last}: {listed}; review them")
    control = snapshot(root, home, files)
    browser = _browser_server(root, home, config, project_exec=project_exec)
    return Setup(
        root,
        config,
        home,
        env,
        tools,
        guard,
        check,
        sections,
        control,
        warnings,
        memory,
        scope,
        servers_here,
        browser,
    )


def _browser_server(root: Path, home: Path, config: Config, *, project_exec: bool) -> Server | None:
    # `[browser] command` is an MCP server that starts only when /browser asks
    # [CLI-29, ADR-0036]; from an untrusted project it does not start at all.
    b = config.browser
    if b.command is None or (not project_exec and from_project(config, root, "browser.")):
        return None
    block = McpSection(command=b.command, args=b.args)
    return servers({"browser": block}, root, home)[0]


def open_memory(home: Path, config: Config) -> Memory:
    return Memory(home / ".edgar" / "memory.db", cap=config.memory.scope_cap)


def toolset(
    root: Path, home: Path, config: Config, *, project_exec: bool
) -> tuple[ToolRegistry, Found, list[Server]]:
    # The session's tools, the skills found and the MCP servers configured. Skills
    # are instructions, not code, so they need no trust; the `skill` tool exists only
    # when there is one to load. Memory's two tools read and propose in this
    # project's scope and the global one.
    found = discover(root, home)
    memory, scope = open_memory(home, config), project_scope(root)
    search = retriever(config.memory.retriever, memory, root)
    extra: list[Tool] = [Remember(memory, scope), Recall(search, [scope, "global"])]
    extra += [SkillTool(found.skills)] if found.skills else []
    # A project's servers run only once the project is trusted [PERM-13]; none of
    # them is started here, so five configured servers cost a cache read [TOOL-8].
    blocks = {
        name: block
        for name, block in config.mcp.items()
        if project_exec or not from_project(config, root, f"mcp.{name}.")
    }
    here = servers(blocks, root, home)
    cached = [tool for server in here for tool in server.tools() or []]
    registry = registry_for(
        root,
        home,
        shell=config.shell.program,
        project_exec=project_exec,
        extra=extra,
        mcp=cached,
        budget=config.tools.schema_budget,
    )
    searchable(registry, [s for s in here if s.tools() is None])
    return registry, found, here


async def authorise_verify(rt: Runtime, session: Session) -> None:
    """The verify command is a shell call, decided before the turn starts, so a run
    that would need a prompt at the end fails now [VER-4]."""
    if rt.verify is None or rt.guard is None:
        return
    decision = await rt.guard.check(
        Shell(rt.verify.program).schema,
        {"command": rt.verify.command},
        cwd=session.cwd,
        mode=session.mode,
        tainted=session.tainted,
        call_id="verify",
        bus=rt.bus,
    )
    if isinstance(decision, Deny):
        raise PermissionDenied(
            f"the verify command `{rt.verify.command}` is not allowed: {decision.reason}",
            hint='allow it with [permissions] shell_allow = ["…"], or run with --mode ask',
        )


def runtime(s: Setup, bus: EventBus, *, choice: Selection | None = None) -> Runtime:
    """The runtime for the configured main model, or for `choice` (`/model`)."""
    config = s.config
    rules = routes_from_config(config.later)  # [[route]] rules, ahead of role binding [ROUTE-2]
    selection = choice or select_model(RoutingContext(), config.model, rules)
    provider, provider_model = resolve(selection.model, config, env=s.env)
    block = config.providers.get(split(selection.model)[0])
    setting = block.prompt_profile if block and block.prompt_profile else config.prompt.profile
    profile = choose_profile(setting, provider.capabilities.max_context)
    bus.emit(ModelSelected(model=selection.model, rule=selection.rule, reason=selection.reason))
    system = load_prompt(s.root, profile_prompt(profile))
    role = config.model.compactor  # auxiliary: only the model the user named [PRV-15]
    # Resolved eagerly, same as the compactor above: [model] fallback names models
    # by "provider/model" string; each one is resolved once, here [ROUTE-7].
    fallback = tuple(
        (name, *resolve(name, config, env=s.env)) for name in chain_from_config(config.later)
    )
    return Runtime(
        provider=provider,
        model=provider_model,
        tools=s.tools,
        system_prompt=system_text(system.text, s.pinned),
        bus=bus,
        max_output_tokens=config.tools.max_output_tokens,
        name=selection.model,
        guard=s.guard,
        verify=s.check,
        context=config.context,
        budget=config.budget,
        compactor=resolve(role, config, env=s.env) if role else None,
        fallback=fallback,
    )


def begin(s: Setup, bus: EventBus, resume: str | None = None) -> tuple[Session, Runtime]:
    """A new session, recorded to disk; or with `resume`, a session id or "" for the
    latest, one replayed from it [CLI-11]. It keeps its model unless --model names one."""
    mode = s.config.permissions.mode
    bus.subscribe(lambda event: _spend(s.home, event))
    if resume is None:
        rt = runtime(s, bus)
        return start(Session(cwd=s.root, model=rt.name, mode=mode)), rt
    session, _ = replay(find(s.root, resume))
    flagged = s.config.origins.get("model.default") == "flag --model"
    rt = runtime(s, bus, choice=None if flagged else Selection(session.model, "resume", "resumed"))
    if session.model != rt.name:
        session.record({"type": "model", "model": rt.name})
    session.mode, session.model = mode, rt.name
    return session, rt


def spending(home: Path) -> Store:
    # The user's spend, across projects, beside trust in ~/.edgar/edgar.db [BUD-2].
    return Store(home / ".edgar" / "edgar.db")


def _spend(home: Path, event: Event) -> None:
    # A turn with a known cost adds to today's; unknown pricing cannot [BUD-5].
    if isinstance(event, TurnFinished) and event.cost and not event.depth:
        spending(home).spend(event.cost)


def daily(s: Setup, rt: Runtime) -> Runtime:
    """What is left of `daily_cost_cap` today becomes this turn's cap, so the loop
    enforces it like the others; with nothing left the turn never starts [BUD-2, BUD-3]."""
    cap = s.config.budget.daily_cost_cap
    if cap is None:
        return rt
    left = cap - sum(cost for _, cost in spending(s.home).spent())
    if left <= 0:
        raise BudgetExceeded(
            f"today's spend reached daily_cost_cap (${cap:.2f})",
            hint="`edgar cost` shows it; the count starts again tomorrow",
        )
    turn = rt.budget.turn_cost_cap
    capped = left if turn is None else min(turn, left)
    return replace(rt, budget=replace(rt.budget, turn_cost_cap=capped))


def finish(s: Setup, session: Session) -> None:
    """Control files that changed while the session ran go in its record, for the
    next session to warn about: a change a human did not see is a change to review."""
    now = snapshot(s.root, s.home, s.config.instructions.files)
    changed = sorted(k for k in s.control.keys() | now.keys() if s.control.get(k) != now.get(k))
    if changed:
        session.record({"type": "control", "changed": changed})
    s.control = now
