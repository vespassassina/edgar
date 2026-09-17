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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar.cli.setup import setup
from edgar.config.load import load
from edgar.config.schema import Config
from edgar.context.builder import Section, build, system_text
from edgar.context.prompts import load_prompt, profile_prompt
from edgar.context.tokens import approx_message_tokens, approx_tokens, message_text
from edgar.core.message import Message
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
