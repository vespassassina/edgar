"""The commands that print or shrink what a session holds [CTX-2, CTX-10].

`edgar context show [ID]` prints the assembled prompt for a session, in order, one
row per section with its token count and the cache breakpoint where it falls. It
reads the same functions `context/builder.py` uses and never calls a provider.
`edgar sessions compact ID` runs `/compact`'s own stages against a stored session.
"""

# edgar context show [ID]:
#   1. the session: the id given, or the latest one in this project
#   2. the prefix, from the same pieces `runtime()` joins into the system message
#   3. one row per prefix section, then the breakpoint, then the messages
#   4. the total, which is the builder's own count of the same prompt
#
# A section's count is its share of the joined system message, taken as the
# difference between two running totals, so the rows add up to the message and the
# message adds up to the prompt: no row is counted twice and none is invented.
#
# edgar sessions compact ID:
#   1. replay the record into the view the user last saw
#   2. run compact(force=True): the same stages /compact runs, no copy of them
#   3. compact() appends one line per stage to the same record, so the history is
#      added to and never rewritten, and --resume replays to the compacted view
#      [CTX-14, ADR-0016]. S2 costs one model call, which is why it says so.

from __future__ import annotations

import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from edgar.cli.setup import setup
from edgar.config.load import load
from edgar.config.schema import Config
from edgar.context.builder import Section, build, system_text
from edgar.context.prompts import load_prompt, profile_prompt
from edgar.context.tokens import approx_message_tokens, approx_tokens, message_text
from edgar.core.message import Message
from edgar.providers.routing import (
    Role,
    Route,
    RoutingContext,
    matches,
    routes_from_config,
    select_model,
)
from edgar.storage.transcript import find, replay

BREAKPOINT = "---- cache breakpoint ----"


@dataclass(frozen=True, slots=True)
class Row:
    name: str
    tokens: int
    detail: str


def rows(prompt: list[Message], sections: list[Section], system: str) -> list[Row]:
    # 1. The prefix: each section's share of the one system message [CTX-17]. The
    #    share is the difference between two running totals of the same join, so the
    #    rows add up to the message however the join itself is spelled.
    out, running = [], 0
    for i, name in enumerate(["system prompt", *(s.name for s in sections)]):
        upto = approx_tokens(system_text(system, sections[:i]))
        out.append(Row(name, upto - running, "frozen for the session"))
        running = upto
    out.append(Row(BREAKPOINT, 0, "everything below here changes within a session"))
    # 2. The rest of the prompt, one row per message, in the builder's order.
    for message in prompt[1:]:
        via = str(message.meta.get("via") or "")
        name = {"summary": "rolling summary", "working": "working state"}.get(via, message.role)
        out.append(Row(name, approx_tokens(message_text(message)), via or "transcript"))
    return out


def context_show(argv: list[str], cwd: Path, home: Path) -> int:
    if argv[:1] != ["show"] or len(argv) > 2:
        print("usage: edgar context show [SESSION]", file=sys.stderr)
        return 2
    config = load(cwd, home=home)
    s = setup(cwd, config, home=home)
    session, _ = replay(find(cwd, argv[1] if len(argv) > 1 else ""))
    # `auto` would pick the compact prompt for a small-window model; naming one here
    # would mean resolving a provider, and this command never does [PRV-17].
    compact = config.prompt.profile == "compact"
    system = load_prompt(cwd, profile_prompt("compact" if compact else "full")).text
    prompt = build(session, system_text(system, s.pinned))
    print(f"{session.id} · {session.model} · {len(session.transcript)} messages")
    for row in rows(prompt, s.pinned, system):
        if row.name == BREAKPOINT:
            print(f"{'':>8}  {row.name}")
            continue
        print(f"{row.tokens:>8,}  {row.name:<18} {row.detail}")
    print(f"{approx_message_tokens(prompt):>8,}  total (approximate, ~4 chars a token)")
    return 0


def sessions_compact(which: str, cwd: Path, home: Path) -> int:
    import asyncio  # only the compacting command awaits anything

    from edgar.cli.setup import runtime as build_runtime
    from edgar.context.compact import compact
    from edgar.core.events import Compacted, EventBus

    s = setup(cwd, load(cwd, home=home), home=home)
    session, _ = replay(find(cwd, which))
    bus = EventBus()
    bus.subscribe(
        lambda e: (
            print(f"{e.stages}: {e.before:,} → {e.after:,} tokens")
            if isinstance(e, Compacted)
            else None
        )
    )
    before = len(session.transcript)
    asyncio.run(compact(session, build_runtime(s, bus), force=True))
    if len(session.transcript) == before:
        print(f"{session.id}: nothing to compact")
        return 0
    print(f"{session.id}: {before} messages → {len(session.transcript)}, appended to the record")
    return 0


# edgar route explain [PROMPT]:
#   1. the [[route]] rules, in the order select_model() reads them
#   2. one row per role: the model it resolves to, the rule that decided, and why
#   3. for the main role, every rule with matched or skipped against that context
#
# It calls `routing.select_model()` — the same pure function a turn calls — and
# prints its `Selection.reason`. No provider is resolved and nothing is sent, so
# this is free and works with no key set [ROUTE-9].
#
# The context it builds is the one the real path builds, not a richer one: the
# main turn (`cli/setup.py`'s `runtime()`) passes a bare `RoutingContext()`, so a
# rule keyed on `mode`, `tags` or `schedule` cannot match for the main role. That
# is a property of edgar, not of this command, so the command shows it rather
# than papering over it with a context no turn would ever use.

ROLES: tuple[Role, ...] = ("main", "subagent", "compactor", "controller", "condenser")


def route_explain(argv: list[str], cwd: Path, home: Path) -> int:
    if argv[:1] != ["explain"]:
        print("usage: edgar route explain [PROMPT]", file=sys.stderr)
        return 2
    config = load(cwd, home=home)
    rules = routes_from_config(config.later)
    tokens = approx_tokens(" ".join(argv[1:]))
    print(f"{len(rules)} [[route]] rules · prompt ~{tokens:,} tokens · no provider contacted")
    for role in ROLES:
        ctx = RoutingContext(role=role, prompt_tokens=tokens)
        chosen = select_model(ctx, config.model, rules)
        print(f"{role:<11} {chosen.model:<32} {chosen.rule:<14} {chosen.reason}")
    main = RoutingContext(prompt_tokens=tokens)
    for rule in rules:
        verdict = "matched" if matches(rule, main) else "skipped"
        print(f"  rule {rule.name:<20} {verdict} for role main: {_conditions(rule)}")
    return 0


def _conditions(rule: Route) -> str:
    # Every condition the rule actually sets, in the config's own spelling.
    set_here = [
        f"{f.name}={getattr(rule, f.name)!r}"
        for f in fields(rule)
        if f.name not in ("name", "model") and getattr(rule, f.name) not in (None, frozenset())
    ]
    return ", ".join(set_here) or "no conditions: it matches anything"


# edgar agents list | validate:
#   list      every agent a session here would find, with its scope and its model
#   validate  every file discovery had to skip, with its path, line and reason
#
# Both read `agents/discovery.py`'s own walk, extensions folded in exactly as a
# session folds them [SUB-1, SUB-2, EXT-8], so what they print is what a turn
# would get. A model of "-" means no `model:` in the file: routing picks one for
# the subagent role, which `edgar route explain` will show.


def agents_command(argv: list[str], cwd: Path, home: Path) -> int:
    from edgar.agents.discovery import discover
    from edgar.cli import trust
    from edgar.extensions.discovery import disabled_from_config
    from edgar.extensions.discovery import discover as discover_extensions
    from edgar.skills.discovery import discover as discover_skills

    if argv not in (["list"], ["validate"]):
        print("usage: edgar agents list | edgar agents validate", file=sys.stderr)
        return 2
    config = load(cwd, home=home)
    found = discover(cwd, home)
    if trust.trusted(cwd, config, home):  # an extension's agents, on the same terms
        discover_extensions(
            cwd, home, discover_skills(cwd, home), found, disabled_from_config(config.later)
        )
    for warning in found.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if argv == ["list"]:
        for agent in found.agents.values():
            print(
                f"{agent.name:<24} {agent.origin:<12} {agent.model or '-':<28} {agent.description}"
            )
        if not found.agents:
            print("no agents; add one as .edgar/agents/NAME.md")
        return 0
    for problem in found.problems:
        print(problem, file=sys.stderr)
    print(f"{len(found.agents)} agents ok, {len(found.problems)} with problems")
    return 1 if found.problems else 0


SECRET = ("api_key", "token", "secret", "password")


def config_show(argv: list[str], cwd: Path, home: Path) -> int:
    # Every effective key, its value and the layer it came from: "default", a config
    # file's path, "env EDGAR_…" or a flag [CFG-2]. A key itself is never in the
    # config, only the name of the variable holding it, so the row for a provider's
    # key says that it is set and nothing more [CFG-6].
    import os

    if argv[:1] != ["show"] or set(argv[1:]) - {"--resolved"}:
        print("usage: edgar config show --resolved", file=sys.stderr)
        return 2
    config = load(cwd, home=home)
    for key in sorted(config.origins):
        print(f"{key:<38} {_render(key, _value(config, key)):<28} {config.origins[key]}")
    for name, block in sorted(config.providers.items()):
        if block.api_key_env and os.environ.get(block.api_key_env):
            print(f"{f'providers.{name}.api_key':<38} {'***':<28} env {block.api_key_env}")
    return 0


def _value(config: Config, key: str) -> Any:
    section, _, rest = key.partition(".")
    holder = getattr(config, section, None)
    if isinstance(holder, dict):  # a [providers.NAME] block, keyed by name
        name, _, rest = rest.rpartition(".")
        holder = holder.get(name)
    return getattr(holder, rest, None) if holder is not None else None


def _render(key: str, value: Any) -> str:
    # A value that holds a credential is never printed, whatever layer set it.
    if value and key.rsplit(".", 1)[-1] in SECRET:
        return "***"
    return "" if value is None else str(value)
