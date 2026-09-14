"""Facts: short durable notes, kept in SQLite and injected as data [MEM-3, MEM-5].

One database for every project, `~/.edgar/memory.db`, so a global fact follows the
user everywhere; a project's facts carry its scope, `project:<hash of its path>`.
The same file holds the search index `recall` reads (recall.py).
"""

# A fact's life:
#
#   add      a human typed it (/remember, memory add)  -> active, provenance "user"
#            the model proposed it (remember)          -> pending, "model-proposed"
#            it nearly repeats an active fact          -> pending, superseding that fact,
#                                                         for a human to settle [MEM-10]
#   confirm  pending -> active; the fact it supersedes becomes superseded
#   forget   -> forgotten
#   evict    a scope over its cap forgets its least useful active facts [MEM-11]
#   undo     every change is logged under an operation number; undo sets the last
#            operation's facts back, and removes the facts it created
#
# A fact's text never changes: an edit is a new fact superseding the old one, so any
# change is a status change and undo can always put it back. Only active facts are
# in the index, so a pending or forgotten fact can never be recalled.

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from edgar.core.errors import UsageError
from edgar.memory.redact import redact
from edgar.storage.db import Store

# The index: porter finds words ("tests" matches "testing"), trigram finds pieces of
# identifiers, paths and error codes, which is what coding sessions search for
# [MEM-24]. Facts and past sessions' turns share it, told apart by `kind`.
SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY, scope TEXT NOT NULL, text TEXT NOT NULL, provenance TEXT NOT NULL,
    confidence REAL NOT NULL, status TEXT NOT NULL, supersedes INTEGER, created REAL NOT NULL,
    used REAL, uses INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS log (op INTEGER NOT NULL, fact INTEGER NOT NULL, old TEXT, new TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS words USING fts5(
    kind UNINDEXED, ref UNINDEXED, scope UNINDEXED, at UNINDEXED, text, tokenize='porter');
CREATE VIRTUAL TABLE IF NOT EXISTS grams USING fts5(
    kind UNINDEXED, ref UNINDEXED, scope UNINDEXED, at UNINDEXED, text, tokenize='trigram');
CREATE TABLE IF NOT EXISTS indexed (path TEXT PRIMARY KEY, size INTEGER NOT NULL,
    turns INTEGER NOT NULL);
"""
INDEXES = ("words", "grams")
COLUMNS = "id, scope, text, provenance, confidence, status, supersedes"
NEAR = 0.5  # word overlap at which a new fact may contradict an old one


@dataclass(frozen=True, slots=True)
class Fact:
    id: int
    scope: str
    text: str
    provenance: str  # user | model-proposed (v2 adds user-prompt, error-template, …)
    confidence: float
    status: str  # pending | active | superseded | forgotten
    supersedes: int | None = None


def project_scope(root: Path) -> str:
    return "project:" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]


def overlap(a: str, b: str) -> float:
    # Shared words over all words: 0.6 for "use pytest for tests" / "use unittest for tests".
    x, y = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(x & y) / len(x | y) if x | y else 0.0


class _Op:
    """One operation: its changes share a number in the log, so undo reverts them together."""

    def __init__(self, db: sqlite3.Connection, number: int) -> None:
        self.db, self.number = db, number

    def insert(self, scope: str, text: str, provenance: str, status: str, sup: int | None) -> int:
        confidence = 1.0 if provenance == "user" else 0.5
        fact = self.db.execute(
            "INSERT INTO facts (scope, text, provenance, confidence, status, supersedes, created)"
            " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (scope, text, provenance, confidence, status, sup, time.time()),
        ).fetchone()[0]
        self.move(fact, status, old=None)
        return int(fact)

    def move(self, fact: int, new: str | None, old: str | None = "") -> None:
        # 1. Log the change; old None means the fact was created, new None that it goes.
        db = self.db
        if old == "":
            old = db.execute("SELECT status FROM facts WHERE id = ?", (fact,)).fetchone()[0]
        db.execute("INSERT INTO log VALUES (?, ?, ?, ?)", (self.number, fact, old, new))
        self.place(fact, new)

    def place(self, fact: int, new: str | None) -> None:
        # 2. Set the status, and keep the index to exactly the active facts.
        db = self.db
        for index in INDEXES:
            db.execute(f"DELETE FROM {index} WHERE kind = 'fact' AND ref = ?", (fact,))
        if new is None:
            db.execute("DELETE FROM facts WHERE id = ?", (fact,))
            return
        db.execute("UPDATE facts SET status = ? WHERE id = ?", (new, fact))
        if new == "active":
            for index in INDEXES:
                db.execute(
                    f"INSERT INTO {index} SELECT 'fact', id, scope, created, text FROM facts"
                    " WHERE id = ?",
                    (fact,),
                )


class Memory(Store):
    schema = SCHEMA

    def __init__(self, path: Path, cap: int = 500) -> None:
        super().__init__(path)
        self.cap = cap  # [memory] scope_cap

    @contextmanager
    def _op(self) -> Iterator[_Op]:
        db = self._db()
        try:
            with db:
                number = db.execute("SELECT COALESCE(MAX(op), 0) + 1 FROM log").fetchone()[0]
                yield _Op(db, int(number))
        finally:
            db.close()

    def facts(self, scopes: list[str], status: tuple[str, ...] = ("active",)) -> list[Fact]:
        marks = ", ".join("?" * len(scopes)), ", ".join("?" * len(status))
        rows = self._rows(
            f"SELECT {COLUMNS} FROM facts WHERE scope IN ({marks[0]}) AND status IN ({marks[1]})"
            " ORDER BY id",
            *scopes,
            *status,
        )
        return [Fact(*row) for row in rows]

    def get(self, fact: int) -> Fact | None:
        rows = self._rows(f"SELECT {COLUMNS} FROM facts WHERE id = ?", fact)
        return Fact(*rows[0]) if rows else None

    def add(self, text: str, scope: str, provenance: str = "user") -> Fact:
        """A new fact; an exact repeat returns the fact already there."""
        # 1. Redact, and collapse whitespace so one fact is one line [MEM-15].
        text = redact(" ".join(text.split()))
        if not text:
            raise UsageError("a fact needs some text")
        # 2. An exact repeat is the same fact; a near one may contradict it [MEM-10].
        active = self.facts([scope])
        same = [f for f in active if f.text.lower() == text.lower()]
        if same:
            return same[0]
        rival = next((f.id for f in active if overlap(f.text, text) >= NEAR), None)
        # 3. Only typed text goes straight to active [MEM-8].
        status = "active" if provenance == "user" and rival is None else "pending"
        with self._op() as op:
            fact = op.insert(scope, text, provenance, status, rival)
            self._evict(op, scope)
        return Fact(
            fact, scope, text, provenance, 1.0 if provenance == "user" else 0.5, status, rival
        )

    def confirm(self, facts: list[int]) -> int:
        """A human said yes: pending facts go active, and replace what they supersede."""
        # 1. Read first: only pending facts can be confirmed, and only once.
        found = [f for f in map(self.get, facts) if f is not None and f.status == "pending"]
        replaced = {f.supersedes for f in found} - {None}
        active = {f.id for f in self.facts(list({f.scope for f in found}))} & replaced
        # 2. Then change them in one operation, so one undo takes it back.
        with self._op() as op:
            for fact in found:
                op.move(fact.id, "active")
                if fact.supersedes in active:
                    op.move(fact.supersedes, "superseded")
                self._evict(op, fact.scope)
        return len(found)

    def forget(self, fact: int) -> bool:
        found = self.get(fact)
        if found is None or found.status not in ("active", "pending"):
            return False
        with self._op() as op:
            op.move(fact, "forgotten")
        return True

    def replace(self, wanted: dict[str, list[tuple[int | None, str]]]) -> int:
        """`memory edit`: make each scope's active facts the edited lines. A changed line
        is a new fact superseding the old; a missing one is forgotten [MEM-4]."""
        # 1. What each id says now, across the edited scopes.
        now = {f.id: f for f in self.facts(list(wanted))}
        changes = 0
        with self._op() as op:
            # 2. Every line: kept as it is, rewritten, or new.
            for scope, lines in wanted.items():
                for fact, text in lines:
                    text = redact(" ".join(text.split()))
                    old = now.pop(fact, None) if fact is not None and text else None
                    if not text or (old and (old.text, old.scope) == (text, scope)):
                        continue
                    op.insert(scope, text, "user", "active", old.id if old else None)
                    if old:
                        op.move(old.id, "superseded")
                    changes += 1
            # 3. Whatever was not in the file any more is forgotten; then the caps hold.
            for gone in now:
                op.move(gone, "forgotten")
            for scope in wanted:
                self._evict(op, scope)
            return changes + len(now)

    def undo(self) -> int:
        """Put back what the last operation changed. Returns how many facts it touched."""
        db = self._db()
        try:
            with db:
                last = db.execute("SELECT MAX(op) FROM log").fetchone()[0]
                rows = db.execute(
                    "SELECT rowid, fact, old FROM log WHERE op = ? ORDER BY rowid DESC", (last,)
                ).fetchall()
                op = _Op(db, 0)
                for _, fact, old in rows:
                    op.place(fact, old)
                db.execute("DELETE FROM log WHERE op = ?", (last,))
                return len({fact for _, fact, _ in rows})
        finally:
            db.close()

    def pinned(self, project: str, limit: int) -> list[Fact]:
        """The session's pinned set, chosen once at its start [MEM-6]: the project's facts
        first, then by confidence, use and recency. Each one chosen counts as a use."""
        rows = self._rows(
            f"SELECT {COLUMNS} FROM facts WHERE scope IN (?, 'global') AND status = 'active'"
            " ORDER BY scope = ? DESC, confidence DESC, uses DESC, COALESCE(used, created) DESC"
            " LIMIT ?",
            project,
            project,
            limit,
        )
        facts = [Fact(*row) for row in rows]
        if facts:
            marks = ", ".join("?" * len(facts))
            sql = f"UPDATE facts SET uses = uses + 1, used = ? WHERE id IN ({marks})"
            self._write(sql, time.time(), *(f.id for f in facts))
        return facts

    def _evict(self, op: _Op, scope: str) -> None:
        # Over the cap, forget the lowest confidence, least recently used first [MEM-11].
        rows = op.db.execute(
            "SELECT id FROM facts WHERE scope = ? AND status = 'active'"
            " ORDER BY confidence, COALESCE(used, created)",
            (scope,),
        ).fetchall()
        for (fact,) in rows[: max(0, len(rows) - self.cap)]:
            op.move(fact, "forgotten")
