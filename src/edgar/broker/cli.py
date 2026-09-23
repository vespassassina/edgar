# edgar receipt [ID] [--refused] [--verify]: the human-readable story behind
# a session's tool calls, replayed from its signed JSONL log [ADR-0039].
# 1. Resolve the session id (bare picks the latest, same as `find()`
#    everywhere else) and locate its receipt file.
# 2. --verify walks the whole chain and exits 1 at the first break.
# 3. Otherwise print one line per entry; --refused narrows to refusals.

from __future__ import annotations

import json
import sys
from pathlib import Path

from edgar.broker.receipt import load_or_create_key, verify
from edgar.storage.transcript import find, sessions_dir

USAGE = "usage: edgar receipt [ID] [--refused] [--verify]"


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    ids = [a for a in argv if not a.startswith("--")]
    if len(ids) > 1:
        print(USAGE, file=sys.stderr)
        return 2
    session_id = find(cwd, ids[0] if ids else "").stem
    path = sessions_dir(cwd) / session_id / "receipt.jsonl"
    if not path.exists():
        print(f"no receipt for {session_id}", file=sys.stderr)
        return 1
    if "--verify" in argv:
        return _verify(path, home or Path.home(), session_id)
    return _tell(path, refused="--refused" in argv)


def _verify(path: Path, home: Path, session_id: str) -> int:
    broken = verify(path, load_or_create_key(home))
    if broken is not None:
        print(f"line {broken.line}: {broken.reason}", file=sys.stderr)
        return 1
    print(f"{session_id}: every line still holds")
    return 0


def _tell(path: Path, refused: bool) -> int:
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(raw)
        if not refused or entry["kind"] == "refuse":
            print(f"{entry['kind']}: {entry['data']}")
    return 0
