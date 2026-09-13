"""`/btw`: a side question that never touches the conversation [CLI-24, ADR-0028].

The request is the one the turn would send, cut back to the last complete unit so
it never ends on unanswered calls, with the question appended and no tools. It
shares the cached prefix. Its deltas go to a private bus, so the turn in progress
keeps the screen; the answer arrives as one `AsideFinished` event.
"""

from __future__ import annotations

from dataclasses import replace

from edgar.context.builder import build
from edgar.core.events import AsideFinished, AsideStarted, EventBus
from edgar.core.loop import Runtime
from edgar.core.message import Message
from edgar.core.session import Session
from edgar.core.units import complete_prefix


def request(session: Session, question: str, system_prompt: str) -> list[Message]:
    snapshot = replace(session, transcript=complete_prefix(session.transcript))
    return [*build(snapshot, system_prompt), Message.user(question)]


async def ask(session: Session, question: str, rt: Runtime) -> str:
    rt.bus.emit(AsideStarted(question=question))
    messages = request(session, question, rt.system_prompt)
    response = await rt.provider.stream(
        messages, [], model=rt.model, bus=EventBus(), reasoning=False
    )
    answer = response.message.text
    rt.bus.emit(AsideFinished(answer=answer, usage=response.usage, cost=response.cost))
    return answer
