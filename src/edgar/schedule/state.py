# FileState: tick.py's State protocol backed by disk, so overlap prevention
# holds across separate `edgar tick` processes, not just within one call
# [SCH-6]. try_lock() creates its file with O_EXCL, the one atomic step even
# when two processes race on the same second; last-run times live in one
# JSON file next to it, read fresh and written whole on every change.

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


class FileState:
    def __init__(self, root: Path) -> None:
        self.dir = root / ".edgar" / "runs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._last_run = self.dir / "last-run.json"

    def last_run(self, name: str) -> datetime | None:
        stamp = self._read().get(name)
        return datetime.fromisoformat(stamp) if stamp else None

    def set_last_run(self, name: str, at: datetime) -> None:
        state = self._read()
        state[name] = at.isoformat()
        self._last_run.write_text(json.dumps(state), encoding="utf-8")

    def try_lock(self, name: str) -> bool:
        try:
            fd = os.open(self._lock(name), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.close(fd)
        return True

    def unlock(self, name: str) -> None:
        self._lock(name).unlink(missing_ok=True)

    def _lock(self, name: str) -> Path:
        return self.dir / f"{name}.lock"

    def _read(self) -> dict[str, str]:
        if not self._last_run.exists():
            return {}
        return dict(json.loads(self._last_run.read_text(encoding="utf-8")))
