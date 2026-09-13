"""Cancel a turn at any moment and the transcript still pairs [CLI-12, TOOL-10, CTX-4].

The M4 done criterion: Ctrl-C during a tool call leaves a transcript that passes
the invariant. Generated here over scripts of tool calls and streamed text, with
the cancel arriving at a generated moment, before, during or after any of them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from harness import runtime, slow_registry, tool_use
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scripted import ScriptedProvider, ScriptedResponse

from edgar.core.aside import request
from edgar.core.loop import run_turn
from edgar.core.message import Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.session import Session
from edgar.core.units import pairing_violations


@st.composite
def steps(draw: st.DrawFn) -> list[ScriptedResponse]:
    out = []
    for n in range(draw(st.integers(0, 3))):
        calls = [
            tool_use("slow", {"seconds": draw(st.sampled_from([0.0, 0.004]))}, id=f"tu_{n}_{i}")
            for i in range(draw(st.integers(1, 3)))
        ]
        out.append(ScriptedResponse(tool_calls=calls, delay_s=draw(st.sampled_from([0, 0.003]))))
    out.append(ScriptedResponse(text="the end of it", stream_chunks=3, stall_s=0.004))
    return out


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(script=steps(), at=st.floats(0, 0.03))
def test_cancel_at_any_moment_leaves_a_valid_transcript(
    tmp_project: Path, script: list[ScriptedResponse], at: float
) -> None:
    session = Session(cwd=tmp_project, model="fake/test", mode="read-only")
    rt = runtime(ScriptedProvider(script), tools=slow_registry())

    async def scenario() -> None:
        task = asyncio.create_task(run_turn(session, "go", rt))
        await asyncio.sleep(at)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert pairing_violations(session.transcript) == []
    last = session.transcript[-1]
    assert not (last.role == "assistant" and last.tool_calls)  # never an unanswered call


@given(cut=st.integers(0, 3))
def test_an_aside_never_sends_unanswered_calls_or_tools(cut: int) -> None:
    session = Session(cwd=Path(), model="fake/test", mode="read-only")
    session.append(Message.user("start"))
    for n in range(cut):
        session.append(Message("assistant", (ToolUseBlock(f"c{n}", "read", {}),)))
        if n < cut - 1:  # the last call is still running
            session.append(Message("tool", (ToolResultBlock(f"c{n}", (TextBlock("ok"),)),)))
    messages = request(session, "quick question", "system")
    assert pairing_violations(messages[1:]) == []
    assert messages[-1].text == "quick question"
    assert len(session.transcript) == 1 + max(0, 2 * cut - 1)  # the session is untouched
