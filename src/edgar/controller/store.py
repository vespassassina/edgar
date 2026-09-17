"""Everything the controller did, and everything it was refused [CTRL-7, CTRL-10]."""

# Two tables in .edgar/controller.db, a project-scoped sibling of learning.db and
# edgar.db, built on storage/db.py's Store for the same reasons it always is: WAL,
# a busy timeout, and a file that does not exist until there is something in it.
#
#   mutations  one row per proposal that had an effect, or would have had one
#   rejected   one row per proposal that never became an action at all
#
# A row's `state` is the whole revert mechanism:
#
#   proposed   dry run: this is what would have changed [CTRL-6]
#   applied    in force
#   reverted   was in force, is not any more
#
# There is deliberately no overrides table. What edgar is actually running under is
# *derived*, by overrides(): the newest `applied` row per action kind wins. So
# reverting is one UPDATE on one row, the log and the state can never disagree, and
# there is no second place to look when they seem to [CTRL-10].

from __future__ import annotations

import time
from dataclasses import dataclass

from edgar.storage.db import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS mutations (
    id INTEGER PRIMARY KEY, at REAL NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL,
    before TEXT NOT NULL, after TEXT NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rejected (
    id INTEGER PRIMARY KEY, at REAL NOT NULL, raw TEXT NOT NULL, problem TEXT NOT NULL);
"""

STATES = ("proposed", "applied", "reverted")

# The two actions whose effect outlives the session, so the two that overrides()
# reads back at the next session's startup. The other six are spent when they
# happen: a warning is printed, an abort ends with the session, a proposal is a
# file on disk, a noop did nothing.
PERSISTED = ("compact", "switch_model")


@dataclass(frozen=True, slots=True)
class Mutation:
    """One row of `edgar controller log`."""

    id: int
    at: float
    action: str
    detail: str  # what changed, in one line, for a human reading the log
    before: str  # the value to put back on revert; "" when there was none
    after: str
    state: str
    reason: str  # the controller's own sentence about why


class Controls(Store):
    schema = SCHEMA

    def record(self, m: Mutation) -> int:
        """Write a mutation and return its id. The id is what `revert` takes."""
        self._write(
            "INSERT INTO mutations VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)",
            m.at or time.time(),
            m.action,
            m.detail,
            m.before,
            m.after,
            m.state,
            m.reason,
        )
        rows = self._rows("SELECT id FROM mutations ORDER BY id DESC LIMIT 1")
        return int(rows[0][0]) if rows else 0

    def mutations(self, limit: int = 20) -> list[Mutation]:
        """The newest first, which is the order a person reads a log in."""
        sql = (
            "SELECT id, at, action, detail, before, after, state, reason "
            "FROM mutations ORDER BY id DESC LIMIT ?"
        )
        return [
            Mutation(int(i), float(at), str(a), str(d), str(b), str(af), str(s), str(r))
            for i, at, a, d, b, af, s, r in self._rows(sql, limit)
        ]

    def mutation(self, mutation_id: int) -> Mutation | None:
        found = [m for m in self.mutations(limit=10_000) if m.id == mutation_id]
        return found[0] if found else None

    def set_after(self, mutation_id: int, after: str) -> bool:
        """The one field written after the row exists: a proposal file is named
        after its own id, so the path is not known until the insert has happened."""
        sql = "UPDATE mutations SET after = ? WHERE id = ?"
        return self.path.exists() and self._write(sql, after, mutation_id) > 0

    def set_state(self, mutation_id: int, state: str) -> bool:
        if state not in STATES:
            return False
        sql = "UPDATE mutations SET state = ? WHERE id = ?"
        return self.path.exists() and self._write(sql, state, mutation_id) > 0

    def overrides(self) -> dict[str, str]:
        """What the next session runs under: the newest applied row per persisted
        action [CTRL-6]. Read by `controller/__init__.py`, which `cli/setup.py`
        reaches by name, so nothing in Core imports this file."""
        # One query rather than one per action: MAX(id) picks the newest row of each
        # kind, and a reverted row is simply not in the answer.
        sql = (
            "SELECT action, after FROM mutations WHERE id IN "
            "(SELECT MAX(id) FROM mutations WHERE state = 'applied' GROUP BY action)"
        )
        found = {str(action): str(after) for action, after in self._rows(sql)}
        return {action: found[action] for action in PERSISTED if action in found}

    def reject(self, raw: str, problem: str) -> None:
        """A proposal that never became an action. Kept because a controller that is
        refused every turn is a configuration problem you want to be able to see."""
        self._write("INSERT INTO rejected VALUES (NULL, ?, ?, ?)", time.time(), raw, problem)

    def rejections(self, limit: int = 20) -> list[tuple[int, float, str, str]]:
        sql = "SELECT id, at, raw, problem FROM rejected ORDER BY id DESC LIMIT ?"
        return [
            (int(i), float(at), str(raw), str(problem))
            for i, at, raw, problem in self._rows(sql, limit)
        ]
