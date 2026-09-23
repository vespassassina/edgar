"""An Intent: the why behind a ticket, from a line a human typed [CAP-1, ADR-0039].

The boundary is the subscription, not a check inside it -- the same shape
`learning/learner.py` uses for MEM-8. Intents reads exactly one event kind,
PromptTyped, at depth 0 only. Everything MEM-9 excludes (tool output, an
@path body, piped stdin, model text, a subagent's own `task` argument)
travels by a different road and is never put into one, so there is nothing
to filter here. PromptSteered is deliberately not read: a correction belongs
to the run already open, so it does not open a fresh Intent [SKL-8c].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from edgar.core.events import Event, PromptTyped
from edgar.core.session import new_id


@dataclass(frozen=True, slots=True)
class Intent:
    id: str
    text: str
    created_at: str  # ISO instant, for the receipt


class Intents:
    """The subscriber. It sees typed lines and nothing else [CAP-1]."""

    def __init__(self) -> None:
        self.current: Intent | None = None

    def __call__(self, event: Event) -> None:
        if not isinstance(event, PromptTyped) or event.depth:
            return
        self.current = Intent(new_id(), event.text, datetime.now(UTC).isoformat())
