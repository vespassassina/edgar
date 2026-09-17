"""The commands that print what edgar would otherwise only do [CTX-2].

`edgar context show [ID]` prints the assembled prompt for a session, in order, one
row per section with its token count and the cache breakpoint where it falls. It
reads the same functions `context/builder.py` uses and never calls a provider.
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

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from edgar.cli.setup import setup
from edgar.config.load import load
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
