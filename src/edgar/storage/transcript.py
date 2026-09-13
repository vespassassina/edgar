"""The session record: `.edgar/sessions/<id>.jsonl`, append-only [CTX-14, ADR-0010].

One JSON object per line, so `tail -f` shows a session as it happens. The first
line describes the session; after it come messages, the changes that reshape the
view (`compaction`, `reset`, `undo`) and the ones that only annotate it (`title`,
`model`, `control`), and a few events: permission decisions (the audit trail, PERM-10),
turn ends with their cost, asides. Nothing is ever rewritten. `replay()` reads
the lines in order and rebuilds the session as the user last saw it.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from edgar.context.compact import apply
from edgar.core import events as ev
from edgar.core.errors import UsageError
from edgar.core.message import ContentBlock, ErrorRecord, Message, TextBlock
from edgar.core.session import Session
from edgar.providers.base import plus

BLOCKS = {cls.__name__: cls for cls in get_args(ContentBlock)}
RECORDED = (ev.PermissionResolved, ev.TurnFinished, ev.AsideStarted, ev.AsideFinished, ev.Compacted)


def sessions_dir(root: Path) -> Path:
    return root / ".edgar" / "sessions"


class Log:
    """Appends to one session's file, created with its first line."""

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
        blocks.append(BLOCKS[raw["kind"]](**b))
    return Message(entry["role"], tuple(blocks), meta=entry.get("meta", {}))


def replay(path: Path) -> tuple[Session, int]:
    """The session as the user last saw it, and how many turns it has run."""
    lines = entries(path)
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
            if "cost" in entry:
                session.cost = plus(session.cost, entry["cost"])
        else:
            session.transcript = apply(session.transcript, entry)
    return start(session), turns


def entries(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def conversation(path: Path) -> list[Message]:
    """Every message of the session, compacted and undone ones included [CLI-25]."""
    return [from_dict(e) for e in entries(path) if e["type"] == "message"]


def control_changes(root: Path) -> tuple[str, list[str]]:
    """The latest session, and the control files that changed while it ran [PERM-12]."""
    found = sorted(sessions_dir(root).glob("*.jsonl"))
    changed = [e["changed"] for e in entries(found[-1]) if e["type"] == "control"] if found else []
    return (found[-1].stem, changed[-1]) if changed else ("", [])


def find(root: Path, which: str) -> Path:
    """`which` is a session id, a unique start of one, or "" for the latest."""
    which = which.upper()
    found = (
        sorted(sessions_dir(root).glob(f"{which}*.jsonl")) if which.isalnum() or not which else []
    )
    if len(found) == 1 or (found and not which):
        return found[-1]
    listed = "several match" if found else "none found"
    raise UsageError(f"session {which!r}: {listed}", hint="edgar sessions list shows them")


def listing(root: Path) -> list[str]:
    """One line per session, newest first: id, date, turns, cost, title [CLI-25]."""
    rows = []
    for path in sorted(sessions_dir(root).glob("*.jsonl"), reverse=True):
        s, turns = replay(path)
        cost = "cost unknown" if s.cost is None else f"${s.cost:.4f}"
        when = s.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        rows.append(f"{s.id}  {when}  {turns:>3} turns  {cost:>12}  {s.title or '(untitled)'}")
    return rows
