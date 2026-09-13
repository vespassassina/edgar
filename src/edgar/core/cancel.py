"""A cancelled turn still leaves a transcript every provider accepts [CLI-12, TOOL-10].

Cancellation is asyncio's: Ctrl-C or `/stop` cancels the task running the turn,
and the loop calls `seal()` before the CancelledError goes on. Every tool call
without a result gets one saying it was cancelled; a stream cut mid-generation
keeps its partial text, marked interrupted, and loses any partial tool call. The
pairing invariant holds afterwards, so the session can go on or be resumed.
"""

from __future__ import annotations

from collections.abc import Sequence

from edgar.core.message import ErrorRecord, Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.session import Session

CANCELLED = "cancelled by user"


def seal(session: Session, *, partial_text: str, results: Sequence[ToolResultBlock]) -> None:
    last = session.transcript[-1] if session.transcript else None
    if last is not None and last.role == "assistant" and last.tool_calls:
        done = {r.tool_use_id: r for r in results}
        blocks = tuple(done.get(c.id) or _cancelled(c) for c in last.tool_calls)
        session.append(Message("tool", blocks))
    elif partial_text:
        session.append(Message("assistant", (TextBlock(partial_text),), meta={"interrupted": True}))


def _cancelled(call: ToolUseBlock) -> ToolResultBlock:
    return ToolResultBlock(
        call.id, (TextBlock(CANCELLED),), is_error=True, error=ErrorRecord(call.name, "cancelled")
    )
