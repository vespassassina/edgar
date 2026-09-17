"""The event bus: the only output path [ADR-0011].

The loop and tools never print. They emit events, and subscribers decide what
reaches the terminal, a JSON stream, a test or a log. That is what lets one loop
serve interactive, piped, embedded and subagent runs. Synchronous and in-process;
a subscriber that needs async work queues it itself.

Event names and fields are part of the 1.0 format freeze [EXT-10].
"""

# How output flows:
#
#   loop, tools, providers ──emit(event)──> EventBus ──> each subscriber, in order
#                                                        ├─ cli/render.py    stdout: the answer
#                                                        ├─ cli/statusbar.py stderr: status
#                                                        ├─ --events writer  one JSON line each
#                                                        └─ tests            record and assert
#
# A typical turn, in the order its events arrive:
#
#   TurnStarted
#     RequestStarted → TextDelta… → RequestFinished        the model answers
#     ToolProposed → PermissionResolved → ToolStarted
#                  → ToolFinished                          once per tool call
#     RequestStarted → TextDelta… → RequestFinished        the model reads the results
#     VerifyStarted → VerifyFinished                       if a check is declared
#   TurnFinished
#
# Each event below says who emits it.

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from edgar.core.message import ErrorRecord
    from edgar.providers.base import Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    # Every event says which agent it came from, so a subagent's output can be
    # told apart from the main loop's (depth 0 is the main loop).
    agent_id: str = "main"
    depth: int = 0

    @property
    def name(self) -> str:
        return type(self).__name__

    # e.g. {"event": "ToolStarted", "agent_id": "main", "depth": 0, "id": "t1", …}
    def to_dict(self) -> dict[str, Any]:
        """The `--events` line: the event's name, then its fields [CLI-18]."""
        return {"event": self.name, **dataclasses.asdict(self)}


Subscriber = Callable[[Event], None]


class EventBus:
    # A list of callables. emit() calls each one, in the order they subscribed,
    # before returning: no queue, no thread, no ordering surprises.
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.remove(subscriber)

    def emit(self, event: Event) -> None:
        for subscriber in self._subscribers:
            subscriber(event)

    def scoped(self, *, agent_id: str, depth: int) -> EventBus:
        """A view stamping every event with a subagent's id and depth, so a
        `task` call (stop 22) needs no change at any existing `emit()` site
        [SUB-3, SUB-9]. Subscribing on the view subscribes on the same bus."""
        return _ScopedBus(self, agent_id=agent_id, depth=depth)


class _ScopedBus(EventBus):
    def __init__(self, inner: EventBus, *, agent_id: str, depth: int) -> None:
        self._inner = inner
        self._agent_id = agent_id
        self._depth = depth

    def subscribe(self, subscriber: Subscriber) -> None:
        self._inner.subscribe(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._inner.unsubscribe(subscriber)

    def emit(self, event: Event) -> None:
        self._inner.emit(dataclasses.replace(event, agent_id=self._agent_id, depth=self._depth))


# lifecycle


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnStarted(Event):
    # core/loop.py, as a turn begins.
    turn_id: str
    model: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnFinished(Event):
    # core/loop.py, as a turn ends, however it ends (reason says how).
    turn_id: str
    usage: Usage
    cost: float | None  # None: some request had unknown pricing [BUD-5]
    reason: str


# provider


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestStarted(Event):
    # core/loop.py, before each request to the model.
    provider: str
    model: str
    input_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TextDelta(Event):
    # The provider adapter, for each piece of answer text as it streams in.
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingDelta(Event):
    # The provider adapter, for each piece of reasoning as it streams in.
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestFinished(Event):
    # core/loop.py, when the model's answer is complete.
    usage: Usage
    cost: float | None  # None: unknown pricing, never a wrong zero [BUD-5]
    cached: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderRetry(Event):
    # providers/http.py, before retrying a failed request.
    attempt: int
    after_s: float
    reason: str  # "HTTP 429", "HTTP 503", "connection error"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReasoningDropped(Event):
    # The provider adapter, when another family's reasoning is left out of a request.
    from_origin: str
    to_family: str  # [PRV-13]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallRepaired(Event):
    # providers/http.py, when a small model's malformed tool call was fixed.
    tool: str
    repair: str  # which fixed repair applied [PRV-16]


# routing [ADR-0013]


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSelected(Event):
    # cli/setup.py, when the model for the session is chosen.
    model: str
    rule: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Fallback(Event):
    # core/loop.py, when a ProviderError sends a request sideways (v1) [ROUTE-7].
    from_model: str
    to_model: str
    reason: str


# tools


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolProposed(Event):
    # tools/execute.py, when a call arrives, before anything is decided.
    id: str
    tool: str
    args_preview: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionResolved(Event):
    """Every decision, with what it was about and why: the audit trail [PERM-10]."""

    # permissions/guard.py, once per tool call, allow or deny.

    id: str
    decision: str  # allow | deny
    source: str  # hard | rule | grant | mode | taint | control | tool | user
    tool: str = ""
    subject: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionTainted(Event):
    # core/loop.py, the first time network content enters the session.
    by_tool: str  # [PERM-11]


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyStarted(Event):
    # core/verify.py, as the declared check starts.
    command: str
    attempt: int  # [VER-6]


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyFinished(Event):
    # core/verify.py, when the check exits.
    ok: bool
    exit_code: int | None
    attempt: int
    duration_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolStarted(Event):
    # tools/execute.py, once the call is allowed and starts running.
    id: str
    tool: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolFinished(Event):
    # tools/execute.py, when the call returns, fails or times out.
    id: str
    tool: str
    ok: bool
    duration_ms: int
    truncated: bool
    blob: str | None
    image: str | None = None  # where the picture it produced was spilled [ADR-0052]
    # What failed, in the four fields the harness computed itself: never the error's
    # text. This is the only thing a learner is allowed to read about a failure, and
    # carrying the record rather than the message is what keeps that true [MEM-22].
    error: ErrorRecord | None = None


# context [CTX-3]


@dataclass(frozen=True, slots=True, kw_only=True)
class Compacted(Event):
    # context/compact.py, after the context was shrunk.
    stages: str  # "S1", "S1+S2", …
    before: int  # tokens
    after: int
    cost: float | None  # the S2 summary call; 0 without one


@dataclass(frozen=True, slots=True, kw_only=True)
class TodoUpdated(Event):
    # tools/builtin/todo.py, when the model replaces the todo list [TOOL-14].
    # Plain dicts, not a Todo type: core/events.py stays below context/ [CTX-18].
    items: tuple[dict[str, str], ...]  # {"text": …, "status": pending|in_progress|done}


# input during a turn [CLI-13]


@dataclass(frozen=True, slots=True, kw_only=True)
class InputQueued(Event):
    # cli/repl.py, when the user types while a turn runs.
    text: str
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SteerApplied(Event):
    # core/loop.py, when a /steer reaches the model at the safe point.
    turn_id: str
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Paused(Event):
    # cli/slash.py, on /pause.
    turn_id: str  # [CLI-27]


@dataclass(frozen=True, slots=True, kw_only=True)
class Resumed(Event):
    # cli/slash.py, on /resume.
    turn_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AsideStarted(Event):
    # core/aside.py, when /btw asks a side question.
    question: str  # [CLI-24]


@dataclass(frozen=True, slots=True, kw_only=True)
class AsideFinished(Event):
    # core/aside.py, with the side answer (never added to the transcript).
    answer: str
    usage: Usage
    cost: float | None


# memory (v1) [MEM-21]


@dataclass(frozen=True, slots=True, kw_only=True)
class FactProposed(Event):
    # tools/builtin/memory_tools.py, when the model calls `remember`: a pending fact,
    # never injected until a human confirms it.
    fact_id: int
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FactSaved(Event):
    # cli/repl.py and cli/slash.py, when a fact goes active. `text` is set when
    # nobody else is about to say what was saved, so a fact the harness learned on
    # its own is shown rather than added quietly (v3) [MEM-8].
    fact_id: int
    provenance: str
    text: str = ""


# learning (v3): the two events the learning path is allowed to read [ADR-0017]


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptTyped(Event):
    """One line a human typed, and nothing else [MEM-8, MEM-9, CLI-3]."""

    # cli/repl.py's submit() and cli/oneshot.py's run_prompt(), at the moment the
    # line arrives and before attach() runs. `text` is the line exactly as typed:
    # never piped stdin, never an @path body, never tool output, never model text.
    # A learner that reads this event and no other text cannot see any of those.
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillsActivated(Event):
    # cli/setup.py's verify_for_turn(), once per turn, naming the skills it loaded,
    # so telemetry can record them without re-deriving the match [MEM-18].
    names: tuple[str, ...]


# controller (v3) [CTRL-3]


@dataclass(frozen=True, slots=True, kw_only=True)
class ControllerActed(Event):
    # controller/gate.py, once per proposal the controller returned. It is the only
    # way the controller reaches a person: it prints nothing itself [ADR-0011].
    action: str  # one of the eight, or "rejected"
    message: str
    mutation_id: int = 0  # the row `edgar controller revert ID` takes; 0 when none


# extensions and hooks [EXT-5]


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStarted(Event):
    # cli/setup.py's begin(), once per session; drives a `session_start` hook.
    session_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEnded(Event):
    # cli/setup.py's finish(); drives a `session_end` hook.
    session_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class HookRan(Event):
    # extensions/hooks.py, once per hook command that actually ran.
    event: str
    command: str
    ok: bool
    vetoed: bool
