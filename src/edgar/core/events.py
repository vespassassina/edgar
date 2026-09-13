"""The event bus: the only output path [ADR-0011].

The loop and tools never print. They emit events, and subscribers decide what
reaches the terminal, a JSON stream, a test or a log. That is what lets one loop
serve interactive, piped, embedded and subagent runs. Synchronous and in-process;
a subscriber that needs async work queues it itself.

Event names and fields are part of the 1.0 format freeze [EXT-10].
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edgar.providers.base import Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    agent_id: str = "main"
    depth: int = 0

    @property
    def name(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, Any]:
        """The `--events` line: the event's name, then its fields [CLI-18]."""
        return {"event": self.name, **dataclasses.asdict(self)}


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.remove(subscriber)

    def emit(self, event: Event) -> None:
        for subscriber in self._subscribers:
            subscriber(event)


# lifecycle


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnStarted(Event):
    turn_id: str
    model: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnFinished(Event):
    turn_id: str
    usage: Usage
    cost: float | None  # None: some request had unknown pricing [BUD-5]
    reason: str


# provider


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestStarted(Event):
    provider: str
    model: str
    input_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TextDelta(Event):
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingDelta(Event):
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestFinished(Event):
    usage: Usage
    cost: float | None  # None: unknown pricing, never a wrong zero [BUD-5]
    cached: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderRetry(Event):
    attempt: int
    after_s: float
    reason: str  # "HTTP 429", "HTTP 503", "connection error"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReasoningDropped(Event):
    from_origin: str
    to_family: str  # [PRV-13]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallRepaired(Event):
    tool: str
    repair: str  # which fixed repair applied [PRV-16]


# routing [ADR-0013]


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSelected(Event):
    model: str
    rule: str
    reason: str


# tools


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolProposed(Event):
    id: str
    tool: str
    args_preview: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionResolved(Event):
    """Every decision, with what it was about and why: the audit trail [PERM-10]."""

    id: str
    decision: str  # allow | deny
    source: str  # hard | rule | grant | mode | taint | control | tool | user
    tool: str = ""
    subject: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionTainted(Event):
    by_tool: str  # [PERM-11]


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyStarted(Event):
    command: str
    attempt: int  # [VER-6]


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyFinished(Event):
    ok: bool
    exit_code: int | None
    attempt: int
    duration_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolStarted(Event):
    id: str
    tool: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolFinished(Event):
    id: str
    ok: bool
    duration_ms: int
    truncated: bool
    blob: str | None


# context [CTX-3]


@dataclass(frozen=True, slots=True, kw_only=True)
class Compacted(Event):
    stages: str  # "S1", "S1+S2", …
    before: int  # tokens
    after: int
    cost: float | None  # the S2 summary call; 0 without one


# input during a turn [CLI-13]


@dataclass(frozen=True, slots=True, kw_only=True)
class InputQueued(Event):
    text: str
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SteerApplied(Event):
    turn_id: str
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Paused(Event):
    turn_id: str  # [CLI-27]


@dataclass(frozen=True, slots=True, kw_only=True)
class Resumed(Event):
    turn_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AsideStarted(Event):
    question: str  # [CLI-24]


@dataclass(frozen=True, slots=True, kw_only=True)
class AsideFinished(Event):
    answer: str
    usage: Usage
    cost: float | None
