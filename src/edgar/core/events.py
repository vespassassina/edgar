"""The event bus: the only output path [ADR-0011].

The loop and tools never print. They emit events, and subscribers decide what
reaches the terminal, a JSON stream, a test or a log. That is what lets one loop
serve interactive, piped, embedded and subagent runs. Synchronous and in-process;
a subscriber that needs async work queues it itself.

Event names and fields are part of the 1.0 format freeze [EXT-10].
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edgar.providers.base import Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    agent_id: str = "main"
    depth: int = 0

    @property
    def name(self) -> str:
        return type(self).__name__


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

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
    cost: float
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
    cost: float
    cached: int


# tools


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolProposed(Event):
    id: str
    tool: str
    args_preview: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionResolved(Event):
    id: str
    decision: str
    source: str  # rule | mode | grant | hook | taint | control


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


# input during a turn [CLI-13]


@dataclass(frozen=True, slots=True, kw_only=True)
class SteerApplied(Event):
    turn_id: str
    text: str
