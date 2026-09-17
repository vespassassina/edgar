"""Working state through a long session and through plan mode [CTX-18, CLI-20, TOOL-14].

The todo list lives on the session, not in the transcript, so compaction cannot
reach it: a 60-turn session that compacts many times must send the same working
block, byte for byte, in every request. Plan mode is the session's own mode set to
read-only, so the permission engine denies a write with no new machinery.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from harness import Recorder, new_session, run_turn_sync, runtime, scripted, tool_use
from scripted import ScriptedResponse

from edgar.config.schema import ContextSection
from edgar.context.working import enter, leave
from edgar.core.events import Compacted, TodoUpdated
from edgar.core.loop import run_turn
from edgar.core.message import Message, TextBlock, ToolUseBlock
from edgar.core.units import pairing_violations
from edgar.providers.base import ProviderResponse, Usage
from edgar.providers.fake import FakeProvider

TODOS = [
    {"text": "read the brief", "status": "done"},
    {"text": "write the code", "status": "in_progress"},
    {"text": "run the check", "status": "pending"},
]


class Busy(FakeProvider):
    """Writes the todo list once, then reads a big file every turn, which fills a
    small window fast and makes the session compact again and again."""

    def __init__(self, window: int = 6000) -> None:
        self.capabilities = replace(FakeProvider.capabilities, max_context=window, max_output=1000)
        self.requests: list[list[Message]] = []
        self.wrote_todos = False

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[Any], **_: Any
    ) -> ProviderResponse:
        if "Blobs worth re-reading" in messages[0].text:  # the compactor's own call
            return self._answer(messages, (TextBlock("Goal: a summary"),))
        self.requests.append(list(messages))
        if not self.wrote_todos:
            self.wrote_todos = True
            return self._answer(messages, (ToolUseBlock("tu_todo", "todo", {"items": TODOS}),))
        done = 0
        for m in reversed(messages):
            if m.role == "user" and not m.meta.get("via"):
                break
            done += len(m.tool_calls)
        if done == 0:
            call = ToolUseBlock(f"tu_{len(self.requests)}", "read", {"path": "big.txt"})
            return self._answer(messages, (call,))
        return self._answer(messages, (TextBlock("done"),))

    def _answer(self, messages: Sequence[Message], content: tuple[Any, ...]) -> ProviderResponse:
        usage = Usage(self.count_tokens(messages), 5, approximate=True)
        stop = "tool_use" if isinstance(content[0], ToolUseBlock) else "end_turn"
        return ProviderResponse(Message("assistant", content), usage, stop, cost=0.0)


def test_the_todo_list_is_byte_identical_in_every_request_of_a_60_turn_session(
    tmp_project: Path,
) -> None:
    (tmp_project / "big.txt").write_text("lorem ipsum " * 170, encoding="utf-8")  # ~500 tokens
    provider, recorder = Busy(), Recorder()
    rt = runtime(provider, recorder)  # type: ignore[arg-type]  # Busy is a Provider
    rt = replace(rt, context=ContextSection(keep_last_turns=2))
    session = new_session(tmp_project)

    async def talk() -> None:
        for n in range(60):
            await run_turn(session, f"turn {n}", rt)

    asyncio.run(talk())
    assert len(recorder.of(Compacted)) > 5  # the window is small; it compacts often
    assert all(pairing_violations(r) == [] for r in provider.requests)

    # The first request is before the model wrote the list; every one after it
    # carries exactly one working block, and always the same bytes [CTX-18].
    blocks = []
    for request in provider.requests[1:]:
        working = [m for m in request if m.meta.get("via") == "working"]
        assert len(working) == 1
        blocks.append(working[0].text)
    assert len(set(blocks)) == 1
    assert "[x] read the brief" in blocks[0] and "[~] write the code" in blocks[0]
    assert "(1/3 done)" in blocks[0]
    assert session.working.todos[1].text == "write the code"
    assert recorder.of(TodoUpdated)[0].items[0]["text"] == "read the brief"


def test_the_working_block_sits_above_the_current_turn_and_not_in_the_transcript(
    tmp_project: Path,
) -> None:
    from edgar.context.builder import build

    session = new_session(tmp_project)
    session.transcript = [Message.user("older"), Message("assistant", (TextBlock("sure"),))]
    prompt = build(session, "system")
    assert [m.meta.get("via") for m in prompt] == [None, None, None]  # nothing to place
    session.working.plan = "do the thing"
    session.transcript.append(Message.user("now"))
    prompt = build(session, "system")
    assert prompt[-2].meta["via"] == "working" and prompt[-1].text == "now"
    block = prompt[-2].content[0]
    assert isinstance(block, TextBlock)
    assert prompt[-2].pinned and block.attached  # never human-typed [MEM-9]
    assert all(m.meta.get("via") != "working" for m in session.transcript)


def test_plan_mode_denies_a_write_and_go_gives_the_mode_back(tmp_project: Path) -> None:
    """[CLI-20, PERM-1] Plan mode is the session's mode, so `decide()` does the work."""
    session = new_session(tmp_project, mode="auto")
    enter(session)
    assert session.mode == "read-only" and session.working.plan_mode
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("write", {"path": "note.txt", "content": "x"})]),
        ScriptedResponse(text="I cannot write in plan mode."),
    )
    run_turn_sync(session, "write the note", runtime(provider))

    result = session.transcript[2].tool_results[0]
    assert result.is_error and result.error is not None
    assert result.error.kind == "permission_denied"
    assert not (tmp_project / "note.txt").exists()
    assert leave(session) == "auto" and not session.working.plan_mode


def test_a_second_plan_never_widens_what_go_restores(tmp_project: Path) -> None:
    """[PERM-1] `/plan` twice must not remember read-only as the mode to go back to."""
    session = new_session(tmp_project, mode="ask")
    enter(session)
    enter(session)
    assert leave(session) == "ask"
