"""The turn loop. Read this first.

Every concern lives in a collaborator: the context builder assembles the prompt,
the provider translates, the tool pipeline validates, decides and runs. What is
left here is the shape of a turn: ask the model, run what it asks for, feed the
results back, and stop when it stops asking. A subagent is this same loop with a
different session (ADR-0006).

Before each request the cost caps are checked and the context compacted if it
has grown too big (context/compact.py). Cancelling the task that runs a turn
(Ctrl-C, `/stop`) seals the transcript first (core/cancel.py). When the model
stops after changing something, the verify gate runs the declared check
(core/verify.py). Still to join: the post-turn gate for v2.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from edgar.config.schema import BudgetSection, ContextSection
from edgar.context.builder import build
from edgar.context.compact import compact
from edgar.core.cancel import seal
from edgar.core.events import (
    Event,
    EventBus,
    RequestFinished,
    RequestStarted,
    SessionTainted,
    SteerApplied,
    TextDelta,
    TurnFinished,
    TurnStarted,
)
from edgar.core.message import Message, TextBlock, ToolResultBlock
from edgar.core.session import Session, new_id
from edgar.core.units import assert_pairing
from edgar.core.verify import Check, verify
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy, category
from edgar.providers.base import Provider, Usage, plus
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
    guard: Guard | None = None  # None: the policy's defaults, nobody to ask
    verify: Check | None = None  # the gate's command, authorised before the turn [VER-4]
    context: ContextSection = field(
        default_factory=ContextSection
    )  # when and how far to compact [CTX-3]
    budget: BudgetSection = field(default_factory=BudgetSection)  # cost caps [BUD-2]
    compactor: tuple[Provider, str] | None = None  # None: the main model writes summaries


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    reason: str  # "completed", "verification_failed" or "budget_exceeded"; a cancel raises
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
    blobs, limit = session.dir / "blobs", rt.max_output_tokens
    ctx = ToolContext(cwd=session.cwd, bus=bus, blob_dir=blobs, max_output_tokens=limit)
    usage = Usage()
    cost: float | None = 0.0  # None once any request's pricing is unknown [BUD-5]
    partial: list[str] = []  # text streamed so far, kept if the turn is cancelled
    results: list[ToolResultBlock] = []
    guard = rt.guard or Guard(Policy(mode=session.mode, cwd=session.cwd, home=Path.home()))
    acted, attempt, reason = False, 0, "completed"  # the verify gate's state [VER-2]
    text = ""  # the last answer: the result, or the partial result a cap leaves [BUD-3]

    def collect(event: Event) -> None:
        if isinstance(event, TextDelta) and event.depth == session.depth:
            partial.append(event.text)

    bus.subscribe(collect)
    try:
        while True:
            # The one safe point: the previous iteration ended on a complete unit, so
            # a steer or a pause never lands between a call and its result [CLI-13].
            await session.wait_if_paused()
            for steer in session.drain_steers():
                bus.emit(SteerApplied(turn_id=turn_id, text=steer))
            caps = rt.budget
            if _over(caps.turn_cost_cap, cost) or _over(caps.session_cost_cap, session.cost):
                reason = "budget_exceeded"
                break
            await compact(session, rt)
            messages = build(session, rt.system_prompt)
            bus.emit(
                RequestStarted(
                    provider=rt.provider.name,
                    model=session.model,
                    input_tokens=rt.provider.count_tokens(messages),
                )
            )
            response = await rt.provider.stream(
                messages, rt.tools.schemas(), model=rt.model, bus=bus
            )
            usage += response.usage
            cost, session.cost = plus(cost, response.cost), plus(session.cost, response.cost)
            cached = response.usage.cache_read_tokens
            bus.emit(RequestFinished(usage=response.usage, cost=response.cost, cached=cached))
            session.append(response.message)
            partial.clear()
            text = response.message.text

            calls = response.message.tool_calls
            if calls:
                # In order, one at a time [TOOL-12]. Failures come back as error
                # results, so the model can recover; nothing here raises.
                results.clear()
                for call in calls:
                    result = await execute(
                        call,
                        registry=rt.tools,
                        ctx=ctx,
                        guard=guard,
                        mode=session.mode,
                        tainted=session.tainted,
                    )
                    results.append(result)
                    acted = acted or _acted(rt, call.name, result)
                    if result.untrusted and not session.tainted:  # sticky [PERM-11]
                        session.tainted = True
                        bus.emit(SessionTainted(by_tool=call.name))
                session.append(Message("tool", tuple(results)))
                assert_pairing(session.transcript)  # [CTX-4]
                continue

            if session.steers_pending():  # the model stopped, but the user steered
                continue
            if rt.verify and acted:  # done means the check passed [VER-2, VER-3]
                attempt += 1
                feedback = await verify(
                    rt.verify,
                    attempt,
                    cwd=session.cwd,
                    blob_dir=ctx.blob_dir,
                    bus=bus,
                    max_tokens=rt.max_output_tokens,
                )
                if feedback is not None and attempt < rt.verify.max_attempts:
                    session.append(Message.user(feedback, via="verify"))
                    continue
                reason = "completed" if feedback is None else "verification_failed"
            break
    except asyncio.CancelledError:
        seal(session, partial_text="".join(partial), results=results)
        assert_pairing(session.transcript)
        bus.emit(TurnFinished(turn_id=turn_id, usage=usage, cost=cost, reason="cancelled"))
        raise
    finally:
        bus.unsubscribe(collect)

    bus.emit(TurnFinished(turn_id=turn_id, usage=usage, cost=cost, reason=reason))
    return TurnResult(text, reason, usage)


def _over(cap: float | None, spent: float | None) -> bool:
    """Unknown spend cannot be shown to be under a cap, so it counts as over [BUD-5]."""
    return cap is not None and (spent is None or spent >= cap)


def _acted(rt: Runtime, name: str, result: ToolResultBlock) -> bool:
    """A non-read tool that actually ran: what makes the verify gate run [VER-2]."""
    tool = rt.tools.get(name)
    refused = result.error is not None and result.error.kind in NOT_RUN
    return tool is not None and category(tool.schema) != "read" and not refused


NOT_RUN = frozenset({"permission_denied", "validation", "not_found"})
