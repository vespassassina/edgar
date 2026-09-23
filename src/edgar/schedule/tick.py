# tick(): one pass over every entry, applying due(), the catch-up policy and
# overlap prevention, calling `runner` for each occurrence that survives
# [SCH-6, SCH-7]. `due()` and `catch_up()` are pure; `tick()` is the seam where
# state (last-run times, the running lock) is read and written — `State` is a
# Protocol so tests use an in-memory fake and production uses a locked file.
#
# 1. Ask due() what fired since last-run, and the catch-up policy how many of
#    those occurrences still need to run.
# 2. Nothing to run: leave the lock alone, still record `now` as last-run so
#    due() starts counting from here next tick.
# 3. Something to run: try_lock() is the one atomic step, so two overlapping
#    `edgar tick` processes cannot both win it. Losing it means an earlier
#    tick is still running this entry — skip the whole entry this pass,
#    last-run untouched, so the occurrences are reconsidered next time.
# 4. Winning it runs every surviving occurrence, unlocks even if the runner
#    raises, then records last-run.

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from edgar.core.errors import ConfigError
from edgar.schedule.due import When, due

CatchUpPolicy = str  # "skip" | "once" | "all" — parser.py validates the value


@dataclass(frozen=True, slots=True)
class Entry:
    name: str
    when: When
    catch_up: CatchUpPolicy = "once"


class State(Protocol):
    def last_run(self, name: str) -> datetime | None: ...
    def set_last_run(self, name: str, at: datetime) -> None: ...
    def try_lock(self, name: str) -> bool: ...
    def unlock(self, name: str) -> None: ...


def catch_up(policy: CatchUpPolicy, occurrences: list[datetime]) -> list[datetime]:
    if not occurrences or policy == "skip":
        return []
    if policy == "once":
        return occurrences[-1:]
    if policy == "all":
        return occurrences
    raise ConfigError(f"schedule: catch-up must be skip, once or all, not {policy!r}")


def tick(
    entries: Iterable[Entry],
    state: State,
    now: datetime,
    runner: Callable[[Entry, datetime], None],
) -> list[str]:
    ran: list[str] = []
    for entry in entries:
        runs = catch_up(entry.catch_up, due(entry.when, state.last_run(entry.name), now))
        if not runs:
            state.set_last_run(entry.name, now)
            continue
        if not state.try_lock(entry.name):
            continue  # still running from an earlier tick [SCH-6]
        try:
            for at in runs:
                runner(entry, at)
                ran.append(entry.name)
        finally:
            state.unlock(entry.name)
        state.set_last_run(entry.name, now)
    return ran
