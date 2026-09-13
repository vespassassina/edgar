"""What `-p` and the REPL share: config, tools, the permission guard, the verify
check, the prompt's prefix, the runtime built from them, and opening and closing
a session."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from edgar.config.load import load, project_config
from edgar.config.schema import Config
from edgar.context.builder import PERSONALITY_WARN, Section, pinned, system_text
from edgar.context.prompts import choose_profile, load_prompt, profile_prompt
from edgar.context.tokens import approx_tokens
from edgar.core.errors import ConfigError, PermissionDenied, UsageError
from edgar.core.events import EventBus, ModelSelected
from edgar.core.loop import Runtime
from edgar.core.session import Session
from edgar.core.verify import Check
from edgar.permissions.control import control_files, snapshot
from edgar.permissions.guard import Asker, Guard
from edgar.permissions.policy import Deny, Policy
from edgar.providers.registry import resolve, split
from edgar.providers.routing import RoutingContext, Selection, select_model
from edgar.storage.db import Store
from edgar.storage.transcript import control_changes, find, replay, start
from edgar.tools.builtin.shell import Shell
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
    tools = registry_for(root, home, shell=config.shell.program, project_exec=project_exec)
    from_project = config.origins.get("verify.command") == str(project_config(root))
    command = verify or (config.verify.command if project_exec or not from_project else None)
    check = Check(command, config.verify.max_attempts, config.shell.program) if command else None
    files = config.instructions.files
    sections = pinned(root, home, files)
    warnings = list(tools.warnings)
    for sec in sections:
        if sec.name == "personality" and approx_tokens(sec.text) > PERSONALITY_WARN:
            warnings.append(f"{sec.source} is ~{approx_tokens(sec.text):,} tokens; keep it short")
    last, changed = control_changes(root)
    if changed:
        listed = ", ".join(changed)
        warnings.append(f"control files changed during session {last}: {listed}; review them")
    control = snapshot(root, home, files)
    return Setup(root, config, home, env, tools, guard, check, sections, control, warnings)


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
    selection = choice or select_model(RoutingContext(), config.model)
    provider, provider_model = resolve(selection.model, config, env=s.env)
    block = config.providers.get(split(selection.model)[0])
    setting = block.prompt_profile if block and block.prompt_profile else config.prompt.profile
    profile = choose_profile(setting, provider.capabilities.max_context)
    bus.emit(ModelSelected(model=selection.model, rule=selection.rule, reason=selection.reason))
    system = load_prompt(s.root, profile_prompt(profile))
    role = config.model.compactor  # auxiliary: only the model the user named [PRV-15]
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
    )


def begin(s: Setup, bus: EventBus, resume: str | None = None) -> tuple[Session, Runtime]:
    """A new session, recorded to disk; or with `resume`, a session id or "" for the
    latest, one replayed from it [CLI-11]. It keeps its model unless --model names one."""
    mode = s.config.permissions.mode
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


def finish(s: Setup, session: Session) -> None:
    """Control files that changed while the session ran go in its record, for the
    next session to warn about: a change a human did not see is a change to review."""
    now = snapshot(s.root, s.home, s.config.instructions.files)
    changed = sorted(k for k in s.control.keys() | now.keys() if s.control.get(k) != now.get(k))
    if changed:
        session.record({"type": "control", "changed": changed})
    s.control = now
