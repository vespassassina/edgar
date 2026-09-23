# run.py: the impure edge between a validated ScheduleEntry and a real turn.
# `as_tick_entries()` projects down to what tick.py needs to do its scheduling
# math; `runner_for()` builds the callback tick() calls once per due
# occurrence [SCH-2, SCH-9]. A scheduled run is always non-interactive, and an
# entry's scope and allowlist become the turn's caveats through the same
# `--scope` mechanism a human types [SCH-8, CAP-4].

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from edgar.cli.oneshot import run_prompt
from edgar.schedule.parser import ScheduleEntry
from edgar.schedule.tick import Entry


def as_tick_entries(entries: tuple[ScheduleEntry, ...]) -> list[Entry]:
    return [Entry(name=e.name, when=e.when, catch_up=e.catch_up) for e in entries]


def runner_for(
    entries: tuple[ScheduleEntry, ...],
    cwd: Path,
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Callable[[Entry, datetime], None]:
    by_name = {e.name: e for e in entries}

    def run(tick_entry: Entry, at: datetime) -> None:
        entry = by_name[tick_entry.name]
        scope = list(entry.scope)
        if entry.allowlist:
            scope.append("tools=" + ",".join(entry.allowlist))
        run_prompt(
            entry.prompt,
            cwd=cwd,
            model=entry.model,
            mode=entry.mode,
            home=home,
            env=env,
            output="text",
            quiet=True,
            verify=entry.verify,
            no_history=True,
            scope=scope or None,
        )

    return run
