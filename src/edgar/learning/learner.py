"""Autolearn: a fact from a line a human typed, and from nothing else [MEM-8, MEM-9]."""

# The boundary is the subscription, not a check inside it.
#
# Learner reads exactly one event, PromptTyped. That event is constructed at two
# call sites, cli/repl.py's submit() and cli/oneshot.py's run_prompt(), each from
# the line the human gave and before context/attach.py runs. Everything the
# boundary excludes travels by a different road and is never put into one:
#
#   piped stdin        run_prompt(attached=…), its own argument [CLI-3]
#   an @path body      Attached.bodies, read after the event is emitted [CLI-3]
#   tool output        a ToolResultBlock in the transcript; no event carries it
#   an error's text    a ToolResultBlock; the bus carries only ErrorRecord [MEM-22]
#   model text         an assistant message, and TextDelta, which is not read here
#
# So there is nothing to filter. This file opens no file, reads no transcript and
# subscribes to no other event; an attacker who controls any of the sources above
# has no path to memory.add() through it [ADR-0017, option B].
#
# What it takes from the line is deliberately narrow: an explicit directive the
# human wrote. Autolearn that guesses is worse than autolearn that misses, because
# a wrong active fact is injected into every later session until someone notices.

from __future__ import annotations

import re

from edgar.core.events import Event, EventBus, FactProposed, FactSaved, PromptTyped
from edgar.memory.store import Memory

# "remember to use uv", "note that the tests need a tmp dir", "keep in mind …".
DIRECTIVE = re.compile(
    r"(?i)\A\s*(?:please\s+)?(?:remember|note|keep in mind)\b[,:]?\s*(?:that\s+)?(.+?)\s*\Z"
)
SHORTEST, LONGEST = 8, 300


def extract(typed: str) -> str | None:
    """The durable note in one typed line, or None. Pure, so the property test can
    drive it with any string at all."""
    # 1. One line only. A pasted block is material the user wanted the model to
    #    read this once, not a rule to keep for every session after it.
    if "\n" in typed:
        return None
    match = DIRECTIVE.match(typed)
    if match is None:
        return None
    # 2. A question asks something; it does not state anything worth keeping.
    text = match[1].strip()
    if text.endswith("?") or not SHORTEST <= len(text) <= LONGEST:
        return None
    return text


class Learner:
    """The subscriber. It sees typed lines and nothing else [MEM-8]."""

    def __init__(self, memory: Memory, *, scope: str, bus: EventBus) -> None:
        self.memory, self.scope, self.bus = memory, scope, bus

    def __call__(self, event: Event) -> None:
        # 1. One event type. Every other event, including every one that could
        #    carry tool output, falls out here.
        if not isinstance(event, PromptTyped):
            return
        text = extract(event.text)
        if text is None:
            return
        # 2. The store decides where it lands: active as `user-prompt`, or pending
        #    when it nearly repeats a fact already there [MEM-10].
        fact = self.memory.add(text, self.scope, provenance="user-prompt")
        # 3. Either way the user is told. A fact added in silence is hidden
        #    behaviour, which is the one thing this project does not ship.
        if fact.status == "active":
            self.bus.emit(FactSaved(fact_id=fact.id, provenance=fact.provenance, text=fact.text))
        else:
            self.bus.emit(FactProposed(fact_id=fact.id, text=fact.text))
