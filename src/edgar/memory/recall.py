"""The built-in retriever: FTS5 over active facts and past sessions [MEM-20, MEM-24].

Lexical and deterministic, so a reader can see why something surfaced: the words
matched. Session search indexes what the user typed and what the model answered,
never tool output or attached files, and catches up lazily, on the first search
that asks for sessions, from where it stopped in each file.
"""

# search(terms, scopes, kinds, limit):
#   1. if sessions are wanted: index whatever was appended to .edgar/sessions/*.jsonl
#      since the last search, from the byte where that file's indexing stopped
#   2. the query is the terms, each quoted, joined by OR
#   3. porter hits first, best BM25 first, the project before global, newest first;
#      then trigram hits porter missed (pieces of identifiers, paths, error codes)
#
# index a session file:
#   read from the stored offset up to the last complete line
#   a user message starts a turn; each text block the user typed or the model wrote
#   is indexed as "SESSION#TURN", redacted; attached text and tool results are not

from __future__ import annotations

import json
from pathlib import Path

from edgar.memory.redact import redact
from edgar.memory.retriever import Hit
from edgar.memory.store import INDEXES, Memory, project_scope

SNIPPET = 400  # characters of a past turn shown per hit


class Fts5Retriever:
    def __init__(self, memory: Memory, root: Path) -> None:
        self.memory, self.root = memory, root
        self.scope = project_scope(root)

    def search(
        self, terms: list[str], scopes: list[str], kinds: list[str], limit: int
    ) -> list[Hit]:
        if "turn" in kinds:
            for path in sorted((self.root / ".edgar" / "sessions").glob("*.jsonl")):
                self.index(path)
        query = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms if t.strip())
        if not query:
            return []
        k, s = ", ".join("?" * len(kinds)), ", ".join("?" * len(scopes))
        hits: dict[tuple[str, str], Hit] = {}
        for index in INDEXES:
            rows = self.memory._rows(
                f"SELECT kind, ref, scope, text FROM {index} WHERE {index} MATCH ?"
                f" AND kind IN ({k}) AND scope IN ({s})"
                " ORDER BY rank, scope = 'global', at DESC LIMIT ?",
                query,
                *kinds,
                *scopes,
                limit,
            )
            for kind, ref, scope, text in rows:
                hits.setdefault((kind, str(ref)), Hit(kind, str(ref), scope, text[:SNIPPET]))
        return list(hits.values())[:limit]

    def index(self, path: Path) -> None:
        # 1. Where this file's indexing stopped, and what was appended since.
        known = self.memory._rows("SELECT size, turns FROM indexed WHERE path = ?", str(path))
        offset, turn = known[0] if known else (0, 0)
        with path.open("rb") as f:
            f.seek(offset)
            data = f.read()
        complete = data[: data.rfind(b"\n") + 1]  # a line still being written waits
        if not complete:
            return
        # 2. The typed and answered text of each new message, turn by turn.
        rows = []
        for line in complete.decode("utf-8").splitlines():
            entry = json.loads(line) if line.strip() else {}
            if entry.get("type") != "message" or entry["role"] not in ("user", "assistant"):
                continue
            turn += entry["role"] == "user"
            for block in entry["content"]:
                if block["kind"] == "TextBlock" and not block.get("attached") and block["text"]:
                    rows.append((f"{path.stem}#{turn}", redact(block["text"])))
        # 3. Written in one transaction with the new offset, so nothing is indexed twice.
        db = self.memory._db()
        try:
            with db:
                for index in INDEXES:
                    db.executemany(
                        f"INSERT INTO {index} VALUES ('turn', ?, ?, ?, ?)",
                        [(ref, self.scope, path.stat().st_mtime, text) for ref, text in rows],
                    )
                db.execute(
                    "INSERT OR REPLACE INTO indexed VALUES (?, ?, ?)",
                    (str(path), offset + len(complete), turn),
                )
        finally:
            db.close()
