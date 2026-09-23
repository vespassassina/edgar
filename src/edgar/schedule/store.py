# SelfSchedules: the `self_schedules` table of the project's edgar.db, the same
# file grants and trust live in, never schedules.toml [SCH-11]. A row is a
# schedule the model created for itself, tagged `[self]` by `schedule list`.
#
# 1. add() writes one row and returns it as a ScheduleEntry, the same currency
#    tick.py and run.py already speak, so a self-schedule runs through the
#    unmodified tick/run path.
# 2. pending_count() backs the pending cap and reads self_schedules itself, so
#    remove() brings it back down. created_since() backs the daily rate limit
#    and reads a separate log that remove() never touches, since "create one,
#    delete it, create another" must still count against the day's limit.

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from edgar.schedule.due import parse_when
from edgar.schedule.parser import ScheduleEntry
from edgar.storage.db import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS self_schedules (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, when_expr TEXT NOT NULL,
    prompt TEXT NOT NULL, mode TEXT NOT NULL, allowlist TEXT NOT NULL,
    scope TEXT NOT NULL, catch_up TEXT NOT NULL, depth INTEGER NOT NULL,
    created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS self_schedule_log (created REAL NOT NULL);
"""

MAX_PENDING = 10  # entries this project may have self-scheduled at once [SCH-11]
MAX_PER_DAY = 20  # new self-schedules created() may accept in a rolling day
MAX_DEPTH = 3  # a self-schedule's run may itself self-schedule this many times


@dataclass(frozen=True, slots=True)
class SelfEntry:
    id: int
    entry: ScheduleEntry
    depth: int


class SelfSchedules(Store):
    schema = SCHEMA

    def list(self) -> list[SelfEntry]:
        cols = "id, name, when_expr, prompt, mode, allowlist, scope, catch_up, depth"
        return [self._row(r) for r in self._rows(f"SELECT {cols} FROM self_schedules ORDER BY id")]

    def pending_count(self) -> int:
        return len(self._rows("SELECT id FROM self_schedules"))

    def created_since(self, seconds: float) -> int:
        sql = "SELECT created FROM self_schedule_log WHERE created >= ?"
        return len(self._rows(sql, time.time() - seconds))

    def add(
        self,
        *,
        name: str,
        when: str,
        prompt: str,
        mode: str,
        allowlist: tuple[str, ...],
        scope: tuple[str, ...],
        catch_up: str,
        depth: int,
    ) -> ScheduleEntry:
        parse_when(when)  # fails before anything is written [SCH-1]
        now = time.time()
        self._write(
            "INSERT INTO self_schedules VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            name,
            when,
            prompt,
            mode,
            ",".join(allowlist),
            ",".join(scope),
            catch_up,
            depth,
            now,
        )
        self._write("INSERT INTO self_schedule_log VALUES (?)", now)
        return ScheduleEntry(
            name=name,
            when=parse_when(when),
            prompt=prompt,
            mode=mode,  # type: ignore[arg-type]  # narrowed by schedule_self's own schema
            allowlist=allowlist,
            catch_up=catch_up,
            scope=scope,
        )

    def remove(self, name: str) -> bool:
        return self._write("DELETE FROM self_schedules WHERE name = ?", name) > 0

    def _row(self, row: tuple[Any, ...]) -> SelfEntry:
        rid, name, when, prompt, mode, allowlist, scope, catch_up, depth = row
        entry = ScheduleEntry(
            name=name,
            when=parse_when(when),
            prompt=prompt,
            mode=mode,
            allowlist=tuple(allowlist.split(",")) if allowlist else (),
            catch_up=catch_up,
            scope=tuple(scope.split(",")) if scope else (),
        )
        return SelfEntry(id=int(rid), entry=entry, depth=int(depth))
