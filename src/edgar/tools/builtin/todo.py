"""`todo`: the model's one way to write working state [TOOL-14, CTX-18, ADR-0025].

The whole list is replaced in one call. There is no add, no complete, no reorder,
because a diff against a list the model cannot see is how todo tools get out of
step with the conversation; sending the list as it should be now cannot.
"""

# todo(items=[{text, status}, …]):
#   replace session.working.todos with exactly these
#   emit TodoUpdated, which the status bar draws and the session log records,
#     so --resume brings the list back
#   answer with the list as it now reads, so the model sees what it wrote
#
# Category "read": it touches no file the user owns, so it never trips the verify
# gate, and it stays available in plan mode, where writing the list is the work.

from __future__ import annotations

from typing import Any

from edgar.context.working import MARKS, STATUSES, Todo
from edgar.core.events import TodoUpdated
from edgar.tools.base import ToolContext, ToolResult, builtin_schema

ITEM = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "one short imperative line"},
        "status": {"type": "string", "enum": list(STATUSES), "default": "pending"},
    },
    "required": ["text"],
}


class TodoTool:
    def __init__(self) -> None:
        self.schema = builtin_schema(
            "todo",
            "Replace the task list for this session with the whole list as it should "
            "read now. Use it for work of several steps: write the list before you "
            "start, and call this again each time a step's status changes. Keep at "
            "most one item in_progress. The list survives compaction.",
            {"items": {"type": "array", "items": ITEM}},
            ["items"],
            category="read",
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.working is None:  # a subagent's context, or an embedded caller
            return ToolResult("this session keeps no todo list", error="not_found")
        items = [
            {"text": str(i["text"]), "status": str(i.get("status", "pending"))}
            for i in args["items"]
        ]
        ctx.working.todos = tuple(Todo(i["text"], i["status"]) for i in items)
        ctx.bus.emit(TodoUpdated(items=tuple(items)))
        rows = "\n".join(f"{MARKS.get(i['status'], MARKS['pending'])} {i['text']}" for i in items)
        return ToolResult(f"the list is now:\n{rows}" if items else "the list is empty")
