"""The turn loop. Read this first.

Every concern lives in a collaborator: the context builder assembles the prompt,
the provider translates, the tool pipeline validates, decides and runs. What is
left here is the shape of a turn: ask the model, run what it asks for, feed the
results back, and stop when it stops asking. A subagent is this same loop with a
different session (ADR-0006).

Still to join, each in its milestone: the budget check and the verify gate (M3),
cancellation (M4), compaction (M5) and the post-turn gate for v2.
"""

from __future__ import annotations

from dataclasses import dataclass

from edgar.context.builder import build
from edgar.core.events import (
    EventBus,
    RequestFinished,
    RequestStarted,
    SteerApplied,
    TurnFinished,
    TurnStarted,
)
from edgar.core.message import Message
from edgar.core.session import Session, new_id
from edgar.core.units import assert_pairing
from edgar.providers.base import Provider, Usage
from edgar.tools.base import ToolContext
from edgar.tools.execute import execute
from edgar.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class Runtime:
    """Everything a turn needs besides the session, resolved once by the caller."""

    provider: Provider
    model: str  # the provider's own model name, e.g. "test" for "fake/test"
    tools: ToolRegistry
    system_prompt: str
    bus: EventBus
    max_output_tokens: int = 8000  # [TOOL-4]


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    reason: str  # "completed"; later "verification_failed", "cancelled"
    usage: Usage


async def run_turn(session: Session, prompt: str, rt: Runtime) -> TurnResult:
    bus = rt.bus
    turn_id = new_id()
    bus.emit(TurnStarted(turn_id=turn_id, model=session.model, depth=session.depth))
    session.append(Message.user(prompt))
    ctx = ToolContext(
        cwd=session.cwd,
        bus=bus,
        blob_dir=session.dir / "blobs",
        max_output_tokens=rt.max_output_tokens,
    )
    usage = Usage()

    while True:
        # The one safe point for /steer: the previous iteration ended on a complete
        # unit, so a steer can never land between a call and its result [CLI-13].
        for text in session.drain_steers():
            bus.emit(SteerApplied(turn_id=turn_id, text=text))
        messages = build(session, rt.system_prompt)
        bus.emit(
            RequestStarted(
                provider=rt.provider.name,
                model=session.model,
                input_tokens=rt.provider.count_tokens(messages),
            )
        )
        response = await rt.provider.stream(messages, rt.tools.schemas(), model=rt.model, bus=bus)
        usage += response.usage
        bus.emit(
            RequestFinished(usage=response.usage, cost=0.0, cached=response.usage.cache_read_tokens)
        )
        session.append(response.message)

        calls = response.message.tool_calls
        if calls:
            # In order, one at a time [TOOL-12]. Failures come back as error
            # results, so the model can recover; nothing here raises.
            results = [
                await execute(call, registry=rt.tools, ctx=ctx, mode=session.mode) for call in calls
            ]
            session.append(Message("tool", tuple(results)))
            assert_pairing(session.transcript)  # [CTX-4]
            continue

        if session.steers_pending():  # the model stopped, but the user steered
            continue
        break

    bus.emit(TurnFinished(turn_id=turn_id, usage=usage, cost=0.0, reason="completed"))
    return TurnResult(response.message.text, "completed", usage)
