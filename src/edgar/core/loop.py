"""The turn loop. Read this first.

Every concern lives in a collaborator: the context builder assembles the prompt,
the provider translates, the tool pipeline validates, decides and runs. What is
left here is the shape of a turn: ask the model, run what it asks for, feed the
results back, and stop when it stops asking. A subagent is this same loop with a
different session (ADR-0006).

Cancelling the task that runs a turn (Ctrl-C, `/stop`) seals the transcript first
(core/cancel.py). Still to join, each in its milestone: the budget check and the
verify gate (M3), compaction (M5) and the post-turn gate for v2.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from edgar.context.builder import build
from edgar.core.cancel import seal
from edgar.core.events import (
    Event,
    EventBus,
    RequestFinished,
    RequestStarted,
    SteerApplied,
    TextDelta,
    TurnFinished,
    TurnStarted,
)
from edgar.core.message import Message, TextBlock, ToolResultBlock
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
    name: str = ""  # the full model string, e.g. "fake/test"


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    reason: str  # "completed"; later "verification_failed", "cancelled"
    usage: Usage


async def run_turn(
    session: Session, prompt: str, rt: Runtime, *, attached: Sequence[str] = ()
) -> TurnResult:
    """`attached` is piped stdin or an @file: context, never the prompt [CLI-3]."""
    bus = rt.bus
    turn_id = new_id()
    bus.emit(TurnStarted(turn_id=turn_id, model=session.model, depth=session.depth))
    wrapped = (f"\n\n<attached>\n{a.rstrip()}\n</attached>" for a in attached)
    blocks = (TextBlock(prompt), *(TextBlock(a, attached=True) for a in wrapped))
    session.append(Message("user", blocks))
    ctx = ToolContext(
        cwd=session.cwd,
        bus=bus,
        blob_dir=session.dir / "blobs",
        max_output_tokens=rt.max_output_tokens,
    )
    usage = Usage()
    cost: float | None = 0.0  # None once any request's pricing is unknown [BUD-5]
    partial: list[str] = []  # text streamed so far, kept if the turn is cancelled
    results: list[ToolResultBlock] = []

    def collect(event: Event) -> None:
        if isinstance(event, TextDelta) and event.depth == session.depth:
            partial.append(event.text)

    bus.subscribe(collect)
    try:
        while True:
            # The one safe point: the previous iteration ended on a complete unit, so
            # a steer or a pause never lands between a call and its result [CLI-13].
            await session.wait_if_paused()
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
            partial.clear()
            response = await rt.provider.stream(
                messages, rt.tools.schemas(), model=rt.model, bus=bus
            )
            usage += response.usage
            cost = None if cost is None or response.cost is None else cost + response.cost
            cached = response.usage.cache_read_tokens
            bus.emit(RequestFinished(usage=response.usage, cost=response.cost, cached=cached))
            session.append(response.message)
            partial.clear()

            calls = response.message.tool_calls
            if calls:
                # In order, one at a time [TOOL-12]. Failures come back as error
                # results, so the model can recover; nothing here raises.
                results.clear()
                for call in calls:
                    results.append(
                        await execute(call, registry=rt.tools, ctx=ctx, mode=session.mode)
                    )
                session.append(Message("tool", tuple(results)))
                assert_pairing(session.transcript)  # [CTX-4]
                continue

            if session.steers_pending():  # the model stopped, but the user steered
                continue
            break
    except asyncio.CancelledError:
        seal(session, partial_text="".join(partial), results=results)
        assert_pairing(session.transcript)
        bus.emit(TurnFinished(turn_id=turn_id, usage=usage, cost=cost, reason="cancelled"))
        raise
    finally:
        bus.unsubscribe(collect)

    bus.emit(TurnFinished(turn_id=turn_id, usage=usage, cost=cost, reason="completed"))
    return TurnResult(response.message.text, "completed", usage)
