"""The plan and the todo list: what the session is working on [CTX-18, ADR-0025].

Memory is slow, confirmed and shared between sessions. Working state is fast,
unconfirmed and gone at the end. It lives on the `Session`, never in
`session.transcript`, so compaction cannot reach it: `compact()` only ever rebuilds
the transcript, which means the pairing invariant (CTX-4) holds here by construction
rather than by care. `build()` renders it into one block just above the current turn,
below the cache breakpoint because it changes.
"""

# What happens where:
#
#   session.working        plan text, todo list, and whether /plan is on
#   render()               that state as one message, or None when there is none
#   place()                inserts it above the last turn start, in build()'s output
#   the JSONL              a TodoUpdated event and a "plan" entry per change, so
#                          --resume brings both back (the *mode* is not restored:
#                          widening a resumed session's policy is a human's to do)
#
# Plan mode is a mode plus a pinned file, not a second engine (ADR-0025). `enter()`
# sets the session's existing mode to read-only and remembers what it was; `leave()`
# puts that back. Nothing automated calls either: /plan, --plan and /go are typed by
# a human, and `leave()` can only restore a mode the session already had, so no tool,
# model or subagent can widen policy through this file (invariant 2).

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from edgar.core.message import Message, TextBlock

if TYPE_CHECKING:  # core/session.py holds a Working, so the import only goes one way
    from edgar.core.session import Session

MARKS = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
STATUSES = tuple(MARKS)
HEADER = (
    "Working state, kept by the harness. It is not part of the conversation and it "
    "survives compaction. Replace the whole todo list with the `todo` tool whenever "
    "it changes; do not describe it in your answer as well."
)


@dataclass(frozen=True, slots=True)
class Todo:
    text: str
    status: str = "pending"  # one of STATUSES


@dataclass
class Working:
    plan: str = ""  # the last plan mode turn's answer, also at sessions/<id>/plan.md
    todos: tuple[Todo, ...] = ()
    plan_mode: bool = False
    previous_mode: str = ""  # what /go puts back; never wider than the session had

    @property
    def empty(self) -> bool:
        return not self.plan and not self.todos


def render(state: Working) -> Message | None:
    # One block, byte-identical between requests until the state itself changes.
    if state.empty:
        return None
    parts = [HEADER]
    if state.plan:
        parts.append("The plan:\n\n" + state.plan.strip())
    if state.todos:
        rows = "\n".join(f"{MARKS.get(t.status, MARKS['pending'])} {t.text}" for t in state.todos)
        parts.append(f"The todo list ({done(state)}/{len(state.todos)} done):\n\n{rows}")
    text = "\n\n".join(parts)
    # attached=True: harness-written context, never something a human typed [MEM-9].
    return Message("user", (TextBlock(text, attached=True),), pinned=True, meta={"via": "working"})


def place(messages: list[Message], state: Working) -> list[Message]:
    # Just above the current turn, which is the last user message that starts one
    # (a steer, a summary or this block carries meta["via"] and starts nothing).
    block = render(state)
    if block is None:
        return messages
    cut = len(messages)
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].role == "user" and not messages[i].meta.get("via"):
            cut = i
            break
    return [*messages[:cut], block, *messages[cut:]]


def done(state: Working) -> int:
    return sum(1 for t in state.todos if t.status == "done")


def summary(state: Working) -> str:
    """For the status bar: "todo 2/5", or nothing at all."""
    return f"todo {done(state)}/{len(state.todos)}" if state.todos else ""


def save_plan(session: Session, text: str) -> None:
    # In plan mode the turn's answer *is* the plan: a file a human can read and edit,
    # and a pinned block that stays after /go [CLI-20].
    if not text.strip():
        return
    session.working.plan = text.strip()
    session.record({"type": "plan", "text": session.working.plan})
    session.dir.mkdir(parents=True, exist_ok=True)
    (session.dir / "plan.md").write_text(session.working.plan + "\n", encoding="utf-8")


def enter(session: Session) -> None:
    """`/plan` or `--plan`: tighten to read-only and remember what to put back."""
    state = session.working
    if not state.plan_mode:
        state.previous_mode = session.mode
    state.plan_mode = True
    session.mode = "read-only"


def leave(session: Session) -> str:
    """`/go`: the mode the session had before `/plan`, never a wider one."""
    state = session.working
    if state.plan_mode:
        session.mode = state.previous_mode or session.mode
        state.plan_mode = False
    return session.mode
