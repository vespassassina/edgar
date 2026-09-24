# The session record: .edgar/sessions/<id>.jsonl, append-only [CTX-14, ADR-0010].
#
# One JSON object per line, so tail -f shows a session as it happens. The first
# line describes the session; after it come messages, the changes that reshape the
# view (compaction, reset, undo) and the ones that only annotate it (title,
# model, control), and a few events: permission decisions (the audit trail, PERM-10),
# turn ends with their cost, asides. Nothing is ever rewritten. replay() reads
# the lines in order and rebuilds the session as the user last saw it.

# A fork (v1) is a file whose second line is {"type": "fork", "parent": ID,
# "at_turn": N}. Its lines are read as the parent's up to the end of turn N, then
# its own, so branching costs one line and the parent is never copied [CLI-22]:
#
#   chain(path)   1. read files upward until one is not a fork
#                 2. read back down: each fork's parent lines up to at_turn, then its own
#
# `/save` writes the chain as one file anyone can load: spilled output inlined,
# secrets redacted. `adopt` makes such a file a session of this project [CLI-25].

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from edgar.context.compact import apply
from edgar.context.working import Todo
from edgar.core import events as ev
from edgar.core.errors import UsageError
from edgar.core.message import (
    ContentBlock,
    ErrorRecord,
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
)
from edgar.core.session import Session
from edgar.memory.redact import redact
from edgar.providers.base import plus

BLOCKS = {cls.__name__: cls for cls in get_args(ContentBlock)}
RECORDED = (
    ev.PermissionResolved,
    ev.TurnFinished,
    ev.AsideStarted,
    ev.AsideFinished,
    ev.Compacted,
    ev.TodoUpdated,  # the record *is* the event, so --resume rebuilds the list [CTX-18]
)


def sessions_dir(root: Path) -> Path:
    return root / ".edgar" / "sessions"


class Log:
    # Appends to one session's file, created with its first line.

    def __init__(self, session: Session) -> None:
        self.path = sessions_dir(session.cwd) / f"{session.id}.jsonl"
        self.head = {"type": "session", "id": session.id, "cwd": str(session.cwd)}
        self.head |= {"model": session.model, "at": session.created_at.isoformat()}

    def write(self, entry: dict[str, Any]) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            ignore = self.path.parent / ".gitignore"  # machine-owned, never committed [CTX-13]
            if not ignore.exists():
                ignore.write_text("*\n", encoding="utf-8")
            self._append(self.head)
        self._append(entry)

    def message(self, message: Message) -> None:
        self.write({"type": "message", **to_dict(message)})

    def event(self, event: ev.Event) -> None:
        if isinstance(event, RECORDED) and not event.depth:
            self.write({"type": "event", **event.to_dict()})

    def _append(self, entry: dict[str, Any]) -> None:
        # newline="" and an explicit \n, or Windows writes \r\n and jq breaks (ADR-0010).
        with self.path.open("a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def start(session: Session) -> Session:
    session.log = Log(session)
    return session


def to_dict(message: Message) -> dict[str, Any]:
    content = [{"kind": type(b).__name__, **asdict(b)} for b in message.content]
    return {"role": message.role, "content": content, "meta": message.meta}


def from_dict(entry: dict[str, Any]) -> Message:
    blocks = []
    for raw in entry["content"]:
        b = {k: v for k, v in raw.items() if k != "kind"}
        if raw["kind"] == "ToolResultBlock":
            b["content"] = tuple(TextBlock(**t) for t in b["content"])
            b["error"] = ErrorRecord(**b["error"]) if b["error"] else None
            # `images` is absent in every session written before M20 [ADR-0060].
            b["images"] = tuple(ImageBlock(**i) for i in b.get("images", ()))
        blocks.append(BLOCKS[raw["kind"]](**b))
    return Message(entry["role"], tuple(blocks), meta=entry.get("meta", {}))


def replay(path: Path) -> tuple[Session, int]:
    # The session as the user last saw it, and how many turns it has run.
    lines = chain(path)
    head, at = lines[0], datetime.fromisoformat(lines[0]["at"])
    session = Session(Path(head["cwd"]), head["model"], "ask", head["id"], at)  # mode: the caller's
    turns = 0
    for entry in lines[1:]:
        kind = entry["type"]
        if kind == "message":
            message = from_dict(entry)
            session.append(message)
            session.tainted |= any(r.untrusted for r in message.tool_results)  # sticky
        elif kind == "title":
            session.title = entry["text"]
        elif kind == "model":
            session.model = entry["model"]
        elif kind == "event":
            turns += entry["event"] == "TurnFinished"
            if entry["event"] == "TodoUpdated":  # working state comes back too [CTX-18]
                session.working.todos = tuple(Todo(**i) for i in entry["items"])
            if "cost" in entry:
                session.cost = plus(session.cost, entry["cost"])
        elif kind == "plan":
            session.working.plan = entry["text"]
        else:
            session.transcript = apply(session.transcript, entry)
    return start(session), turns


def entries(path: Path) -> list[dict[str, Any]]:
    # Every line ends in "\n" once written whole, so whatever follows the last
    # "\n" is a line a crash tore mid-write: drop it, keep the rest. A bad line
    # anywhere else is real damage and still raises [ADR-0010, BLUEPRINT §3.4].
    lines = path.read_text(encoding="utf-8").split("\n")[:-1]
    return [json.loads(line) for line in lines if line]


def conversation(path: Path) -> list[Message]:
    # Every message of the session, compacted and undone ones included [CLI-25].
    return [from_dict(e) for e in chain(path) if e["type"] == "message"]


def chain(path: Path) -> list[dict[str, Any]]:
    # A session's lines; a fork's begin with its parent's, up to its turn [CLI-22].
    # 1. Up: each fork names its parent in its second line.
    files = [entries(path)]
    while len(files[-1]) > 1 and files[-1][1]["type"] == "fork":
        files.append(entries(path.with_name(f"{files[-1][1]['parent']}.jsonl")))
    # 2. Down: the parent's lines to the end of turn at_turn, then the fork's own.
    lines = files.pop()
    while files:
        own = files.pop()
        lines = [own[0], *lines[1 : _upto(lines, own[1]["at_turn"])], *own[2:]]
    return lines


def _upto(lines: list[dict[str, Any]], turn: int) -> int:
    # Just past the line that ends turn `turn`; turn 0 is before the first.
    ends = [i + 1 for i, e in enumerate(lines) if e.get("event") == "TurnFinished"]
    return ends[turn - 1] if turn else 1


def fork(root: Path, which: str) -> Path:
    # --fork ID[@TURN], /fork: a new session that starts as ID did at the end
    # of TURN (default: its latest). The parent is untouched [CLI-22].
    name, _, at = which.partition("@")
    parent = find(root, name)
    base, turns = replay(parent)
    turn = int(at) if at.isdigit() else turns
    if at and not (at.isdigit() and turn <= turns):
        raise UsageError(f"{which!r}: {base.id} has turns 0 to {turns}")
    child = start(Session(cwd=root, model=base.model, mode="ask"))
    child.record({"type": "fork", "parent": parent.stem, "at_turn": turn})
    return sessions_dir(root) / f"{child.id}.jsonl"


def save(path: Path, out: Path) -> int:
    # /save: the session as one portable file, spilled output inlined and secrets
    # redacted (MEM-15). Returns how many lines it wrote [CLI-25].
    lines = []
    for entry in chain(path):
        if entry["type"] == "message":
            entry = {"type": "message", **to_dict(_inline(from_dict(entry)))}
        lines.append(json.dumps(_scrub(entry), ensure_ascii=False, default=str))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return len(lines)


def _inline(message: Message) -> Message:
    # A spilled result carries its full output in the file, not a path to it.
    blocks = []
    for b in message.content:
        if isinstance(b, ToolResultBlock) and b.blob and Path(b.blob).is_file():
            full = TextBlock(Path(b.blob).read_text(encoding="utf-8"))
            b = replace(b, content=(full,), truncated=False, blob=None)
        blocks.append(b)
    return replace(message, content=tuple(blocks))


def _scrub(entry: dict[str, Any]) -> dict[str, Any]:
    # Redact every string in the entry, however deeply nested, with a stack rather
    # than recursion. String by string, so a pattern never spans JSON syntax.
    # `asdict` keeps a block's tuples: each becomes a list so it can be changed.
    stack: list[Any] = [entry]
    while stack:
        node = stack.pop()
        for key in node.keys() if isinstance(node, dict) else range(len(node)):
            value = node[key]
            if isinstance(value, str):
                node[key] = redact(value)
            elif isinstance(value, dict | list | tuple):
                node[key] = value if isinstance(value, dict) else list(value)
                stack.append(node[key])
    return entry


def forks(path: Path) -> list[str]:
    # The sessions that branch from this one, and so read its file [CLI-22].
    found = []
    for other in path.parent.glob("*.jsonl"):
        # The fork line is always the second: read no further.
        with other.open(encoding="utf-8") as f:
            f.readline()
            second = json.loads(f.readline() or "{}")
        if second.get("parent") == path.stem:
            found.append(other.stem)
    return sorted(found)


def adopt(root: Path, saved: Path) -> Path:
    # --load PATH, /load PATH: a saved file becomes a new session here.
    if not saved.is_file():
        raise UsageError(f"{saved} is not a file", hint="/save writes one")
    lines = entries(saved)
    session = start(Session(cwd=root, model=lines[0]["model"], mode="ask"))
    for entry in lines[1:]:
        session.record(entry)
    return sessions_dir(root) / f"{session.id}.jsonl"


def control_changes(root: Path) -> tuple[str, list[str]]:
    # The latest session, and the control files that changed while it ran [PERM-12].
    found = sorted(sessions_dir(root).glob("*.jsonl"))
    changed = [e["changed"] for e in entries(found[-1]) if e["type"] == "control"] if found else []
    return (found[-1].stem, changed[-1]) if changed else ("", [])


def find(root: Path, which: str) -> Path:
    # `which` is a session id, a unique start of one, or "" for the latest.
    which = which.upper()
    found = (
        sorted(sessions_dir(root).glob(f"{which}*.jsonl")) if which.isalnum() or not which else []
    )
    if len(found) == 1 or (found and not which):
        return found[-1]
    listed = "several match" if found else "none found"
    raise UsageError(f"session {which!r}: {listed}", hint="edgar sessions list shows them")


def listing(root: Path) -> list[str]:
    # One line per session, newest first: id, date, turns, cost, title [CLI-25].
    rows = []
    for path in sorted(sessions_dir(root).glob("*.jsonl"), reverse=True):
        s, turns = replay(path)
        cost = "cost unknown" if s.cost is None else f"${s.cost:.4f}"
        when = s.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        rows.append(f"{s.id}  {when}  {turns:>3} turns  {cost:>12}  {s.title or '(untitled)'}")
    return rows
