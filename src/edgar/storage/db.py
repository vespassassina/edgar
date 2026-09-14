"""SQLite for what edgar remembers between sessions: grants and trust [PERM-6, PERM-13].

Grants live in the project's `.edgar/edgar.db`, trust in `~/.edgar/edgar.db`; never
in a config file. WAL mode, short transactions and a busy timeout, because the
database may sit in a folder a sync client is watching. The file is created only
when there is something to store.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    id INTEGER PRIMARY KEY, tool TEXT NOT NULL, subject TEXT NOT NULL, created REAL NOT NULL,
    UNIQUE (tool, subject));
CREATE TABLE IF NOT EXISTS trust (
    project TEXT PRIMARY KEY, digest TEXT NOT NULL, created REAL NOT NULL);
"""


class Store:
    schema = SCHEMA  # memory/store.py reuses the class with its own tables

    def __init__(self, path: Path) -> None:
        self.path = path

    def _db(self) -> sqlite3.Connection:
        # Open, creating the file and its tables on first use.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5.0)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(self.schema)
        return db

    def _rows(self, sql: str, *args: object) -> list[Any]:
        if not self.path.exists():
            return []
        db = self._db()
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def _write(self, sql: str, *args: object) -> int:
        db = self._db()
        try:
            with db:
                return db.execute(sql, args).rowcount
        finally:
            db.close()

    def grants(self) -> list[tuple[int, str, str, float]]:
        rows = self._rows("SELECT id, tool, subject, created FROM grants ORDER BY id")
        return [(int(i), str(t), str(s), float(c)) for i, t, s, c in rows]

    def grant(self, tool: str, subject: str) -> None:
        self._write(
            "INSERT OR IGNORE INTO grants VALUES (NULL, ?, ?, ?)", tool, subject, time.time()
        )

    def revoke(self, grant_id: int) -> bool:
        return self.path.exists() and self._write("DELETE FROM grants WHERE id = ?", grant_id) > 0

    def trusted(self, project: Path, digest: str) -> bool:
        rows = self._rows("SELECT digest FROM trust WHERE project = ?", str(project))
        return bool(rows) and rows[0][0] == digest

    def trust(self, project: Path, digest: str) -> None:
        self._write(
            "INSERT OR REPLACE INTO trust VALUES (?, ?, ?)", str(project), digest, time.time()
        )
