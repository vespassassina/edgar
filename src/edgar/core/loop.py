# The turn loop. Read this first.
#
# Every concern lives in a collaborator: the context builder assembles the prompt,
# the provider translates, the tool pipeline validates, decides and runs. What is
# left here is the shape of a turn: ask the model, run what it asks for, feed the
# results back, and stop when it stops asking. A subagent is this same loop with a
# different session (ADR-0006).
#
# Before each request the cost caps are checked and the context compacted if it
# has grown too big (context/compact.py). Cancelling the task that runs a turn
# (Ctrl-C, `/stop`) seals the transcript first (core/cancel.py). When the model
# stops after changing something, the verify gate runs the declared check
# (core/verify.py). Escalation (providers/escalation.py) walks the model chain
# upward on repeated failure; fallback (providers/fallback.py) moves sideways on
# a provider outage. Neither is the other [ADR-0013].

# The whole turn, as pseudocode:
#
#   record what the human typed
#   repeat:
#       apply any pause or /steer            (only here, between whole units)
#       if a cost cap is reached:            stop, keep the last answer
#       compact the context if it is too big
#       ask the model, streaming its answer
#       if it asked for tools:
#           run each call in order, record the results
#           go round again
#       if the user steered meanwhile:       go round again
#       if it changed something and a check is declared:
#           run the check
#           if it failed and attempts remain: show the model why, go round again
#       stop
#   announce how the turn ended and return the answer
#
# Cancelling at any point seals the transcript so every call has a result.

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from edgar.config.schema import BudgetSection, ContextSection
from edgar.context.builder import build
from edgar.context.compact import compact
from edgar.core.cancel import seal
from edgar.core.errors import ProviderError
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
from edgar.core.message import ImageBlock, Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.session import Session, new_id
from edgar.core.units import assert_pairing
from edgar.core.verify import Check, verify
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy, category
from edgar.providers.base import Provider, Usage, plus
from edgar.providers.fallback import next_provider
from edgar.tools.base import ToolContext, build_context
from edgar.tools.execute import execute_many
from edgar.tools.registry import ToolRegistry

# What a caller may hand a turn beside the prompt: attached text, and pictures.
Texts = Sequence[str]
Shots = Sequence[ImageBlock]


class _Escalator(Protocol):
    # v3's shape, not its import: `providers/escalation.py` is removable [NFR-12],
    # so this file never names it. `EscalationState` matches this structurally.
    def current(self, rt: Runtime) -> tuple[Provider, str, str]: ...
    def after_round(self, rt: Runtime, turn: _Turn) -> None: ...


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
    context: ContextSection = field(default_factory=ContextSection)  # compact timing [CTX-3]
    budget: BudgetSection = field(default_factory=BudgetSection)  # cost caps [BUD-2]
    compactor: tuple[Provider, str] | None = None  # None: the main model writes summaries
    fallback: tuple[tuple[str, Provider, str], ...] = ()  # (name, provider, its model) [ROUTE-7]
    escalation: _Escalator | None = None  # v3, upward on repeated failure [ROUTE-5]
    hooks: tuple[object, ...] = ()  # `[[hooks]]` rules; opaque here, typed in tools/base.py [EXT-4]


@dataclass(frozen=True, slots=True)
class TurnResult:
    text: str
    reason: str  # "completed", "verification_failed" or "budget_exceeded"; a cancel raises
    usage: Usage


@dataclass(slots=True)
class _Turn:
    # What one turn keeps track of while it runs. The helpers below read and
    # update it, so each of them stays one level deep.
    id: str
    ctx: ToolContext  # what every tool call gets: cwd, bus, where to spill
    guard: Guard  # the permission engine, plus whoever answers its prompts
    usage: Usage = field(default_factory=Usage)
    cost: float | None = 0.0  # None once any request's pricing is unknown [BUD-5]
    partial: list[str] = field(default_factory=list)  # streamed text, kept on cancel
    results: list[ToolResultBlock] = field(default_factory=list)  # this round's results
    acted: bool = False  # a non-read tool ran: the verify gate will run [VER-2]
    attempt: int = 0  # verify attempts so far
    text: str = ""  # the last answer: the result, or what a cap leaves [BUD-3]
    tried: set[str] = field(default_factory=set)  # models a ProviderError already ruled out
    reasoning: bool = True  # False once fallback crosses families [PRV-13]


async def run_turn(
    session: Session, prompt: str, rt: Runtime, *, attached: Texts = (), images: Shots = ()
) -> TurnResult:
    # `attached` is piped stdin or an @file: context, never the prompt [CLI-3].
    # `images` are the pictures an @photo.png resolved to [ADR-0052].
    # 1. Record what the human typed, with anything attached marked as attached.
    turn = _start(session, prompt, rt, attached, images)
    reason = "completed"

    # 2. Keep the text as it streams in, so a cancel can save what was said.
    def collect(event: Event) -> None:
        if isinstance(event, TextDelta) and event.depth == session.depth:
            turn.partial.append(event.text)

    rt.bus.subscribe(collect)
    try:
        while True:
            # 3. The one safe point: the previous round ended on a complete unit,
            #    so a steer or a pause never lands between a call and its result
            #    [CLI-13].
            await session.wait_if_paused()
            for steer in session.drain_steers():
                rt.bus.emit(SteerApplied(turn_id=turn.id, text=steer))

            # 4. Out of money? Stop here and keep the last answer [BUD-3].
            if _capped(session, rt, turn):
                reason = "budget_exceeded"
                break

            # 5. Ask the model. It answers with text, tool calls, or both.
            answer = await _ask(session, rt, turn)

            # 6. It asked for tools: run them, then go round again with the results.
            if answer.tool_calls:
                await _run_tools(answer.tool_calls, session, rt, turn)
                if rt.escalation:
                    rt.escalation.after_round(rt, turn)
                continue

            # 7. It stopped, but the user steered in the meantime: go round again.
            if session.steers_pending():
                continue

            # 8. It stopped after changing something: done means the check passes
            #    [VER-2, VER-3]. A failure goes back to the model while attempts remain.
            if rt.verify and turn.acted:
                feedback = await _check(rt.verify, session, rt, turn)
                if feedback is not None and turn.attempt < rt.verify.max_attempts:
                    session.append(Message.user(feedback, via="verify"))
                    continue
                reason = "completed" if feedback is None else "verification_failed"

            # 9. Nothing left to do.
            break
    except asyncio.CancelledError:
        # Cancelled mid-turn: give every open call a result and keep the partial
        # answer, so the transcript is valid for the next request [CTX-4].
        seal(session, partial_text="".join(turn.partial), results=turn.results)
        assert_pairing(session.transcript)
        rt.bus.emit(
            TurnFinished(turn_id=turn.id, usage=turn.usage, cost=turn.cost, reason="cancelled")
        )
        raise
    finally:
        rt.bus.unsubscribe(collect)

    # 10. Announce how the turn ended and hand back the answer.
    rt.bus.emit(TurnFinished(turn_id=turn.id, usage=turn.usage, cost=turn.cost, reason=reason))
    return TurnResult(turn.text, reason, turn.usage)


def _start(session: Session, prompt: str, rt: Runtime, attached: Texts, images: Shots) -> _Turn:
    # Announce the turn.
    turn_id = new_id()
    rt.bus.emit(TurnStarted(turn_id=turn_id, model=session.model, depth=session.depth))
    # The prompt is one block; each attachment is its own block, tagged as attached
    # so nothing downstream mistakes it for something the human typed.
    wrapped = (f"\n\n<attached>\n{a.rstrip()}\n</attached>" for a in attached)
    # A picture rides beside the typed line as its own block, in the same message.
    blocks: list[TextBlock | ImageBlock] = [TextBlock(prompt), *images]
    blocks.extend(TextBlock(a, attached=True) for a in wrapped)
    session.append(Message("user", tuple(blocks)))
    # Set up what tool calls share for the whole turn.
    ctx = build_context(session, rt)
    guard = rt.guard or Guard(Policy(mode=session.mode, cwd=session.cwd, home=Path.home()))
    return _Turn(id=turn_id, ctx=ctx, guard=guard)


def _capped(session: Session, rt: Runtime, turn: _Turn) -> bool:
    # Either cap reached: this turn's spend, or the whole session's.
    caps = rt.budget
    return _over(caps.turn_cost_cap, turn.cost) or _over(caps.session_cost_cap, session.cost)


async def _ask(session: Session, rt: Runtime, turn: _Turn) -> Message:
    # 1. Make room first if the context has grown past `compact_at` [CTX-3].
    await compact(session, rt)
    # 2. Build the request: system prompt, then the (possibly compacted) view.
    messages = build(session, rt.system_prompt)
    # 3. Stream the answer, falling back sideways on a ProviderError [ROUTE-7].
    #    Retries and backoff already ran inside stream(); reaching here means
    #    that is exhausted, or the failure was never retryable.
    default = (rt.provider, rt.model, rt.name)
    provider, model, name = rt.escalation.current(rt) if rt.escalation else default
    while True:
        tokens = provider.count_tokens(messages)
        rt.bus.emit(RequestStarted(provider=provider.name, model=name, input_tokens=tokens))
        try:
            response = await provider.stream(
                messages, rt.tools.schemas(), model=model, bus=rt.bus, reasoning=turn.reasoning
            )
            break
        except ProviderError as exc:
            required = bool(rt.tools.schemas())
            provider, model, name, turn.reasoning = next_provider(
                name, provider, exc, rt.fallback, turn.tried, tools_required=required, bus=rt.bus
            )
    # 4. Add up what it cost, for the turn and for the session.
    turn.usage += response.usage
    turn.cost, session.cost = plus(turn.cost, response.cost), plus(session.cost, response.cost)
    cached = response.usage.cache_read_tokens
    rt.bus.emit(RequestFinished(usage=response.usage, cost=response.cost, cached=cached))
    # 5. Record the answer. What streamed is now in the transcript, so drop the copy.
    session.append(response.message)
    turn.partial.clear()
    turn.text = response.message.text
    return response.message


async def _run_tools(
    calls: Sequence[ToolUseBlock], session: Session, rt: Runtime, turn: _Turn
) -> None:
    # In order, except consecutive `task` calls fan out together [TOOL-12].
    # Failures come back as error results, so the model can recover.
    turn.results.clear()
    limits = getattr(rt.tools.get("task"), "limits", None)
    results = await execute_many(
        calls,
        registry=rt.tools,
        ctx=turn.ctx,
        guard=turn.guard,
        mode=session.mode,
        tainted=session.tainted,
        max_parallel=getattr(limits, "max_parallel", 1),
    )
    for call, result in zip(calls, results, strict=True):
        turn.results.append(result)
        # 1. Remember whether anything changed, for the verify gate.
        turn.acted = turn.acted or _acted(rt, call.name, result)
        # 2. Content from the network taints the session, for good [PERM-11].
        if result.untrusted and not session.tainted:
            session.tainted = True
            rt.bus.emit(SessionTainted(by_tool=call.name))
    # All results go back in one tool message, right after the calls [CTX-4].
    session.append(Message("tool", tuple(turn.results)))
    assert_pairing(session.transcript)


async def _check(check: Check, session: Session, rt: Runtime, turn: _Turn) -> str | None:
    # Run the declared check once more. None means it passed; otherwise the
    # feedback to show the model.
    turn.attempt += 1
    return await verify(
        check,
        turn.attempt,
        cwd=session.cwd,
        blob_dir=turn.ctx.blob_dir,
        bus=rt.bus,
        max_tokens=rt.max_output_tokens,
    )


def _over(cap: float | None, spent: float | None) -> bool:
    # Unknown spend cannot be shown to be under a cap, so it counts as over [BUD-5].
    return cap is not None and (spent is None or spent >= cap)


def _acted(rt: Runtime, name: str, result: ToolResultBlock) -> bool:
    # A non-read tool that actually ran: what makes the verify gate run [VER-2].
    tool = rt.tools.get(name)
    refused = result.error is not None and result.error.kind in NOT_RUN
    return tool is not None and category(tool.schema) != "read" and not refused


# Error kinds that mean the tool never ran, so it cannot have changed anything.
NOT_RUN = frozenset({"permission_denied", "validation", "not_found"})
