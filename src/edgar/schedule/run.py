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
    depths: Mapping[str, int] | None = None,
) -> Callable[[Entry, datetime], None]:
    """`depths` names the entries that came from `self_schedules`, not
    schedules.toml: their run gets `EDGAR_SCHEDULE_SELF_DEPTH` set, the marker
    schedule_self reads to enforce its own nesting ceiling [SCH-11]."""
    by_name = {e.name: e for e in entries}

    def run(tick_entry: Entry, at: datetime) -> None:
        entry = by_name[tick_entry.name]
        scope = list(entry.scope)
        if entry.allowlist:
            scope.append("tools=" + ",".join(entry.allowlist))
        run_env = dict(env or {})
        if depths and tick_entry.name in depths:
            run_env["EDGAR_SCHEDULE_SELF_DEPTH"] = str(depths[tick_entry.name])
        run_prompt(
            entry.prompt,
            cwd=cwd,
            model=entry.model,
            mode=entry.mode,
            home=home,
            env=run_env or None,
            output="text",
            quiet=True,
            verify=entry.verify,
            no_history=True,
            scope=scope or None,
        )

    return run
