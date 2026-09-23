"""tick() driving a real turn on the fake provider, through run.py [SCH-2,
SCH-8, SCH-9]."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from edgar.schedule.due import Interval
from edgar.schedule.parser import ScheduleEntry
from edgar.schedule.run import as_tick_entries, runner_for
from edgar.schedule.state import FileState
from edgar.schedule.tick import tick

NOW = datetime(2026, 9, 23, 9, 0)


def test_a_due_entry_runs_a_real_turn_and_prints_its_answer(
    tmp_project: Path, home: Path, capsys: object
) -> None:
    entries = (
        ScheduleEntry(
            name="read-a",
            when=Interval(60),
            prompt="read a.txt",
            mode="read-only",
            model="fake/test",
        ),
    )
    state = FileState(tmp_project)
    ran = tick(
        as_tick_entries(entries),
        state,
        NOW,
        runner_for(entries, tmp_project, home=home, env={}),
    )
    assert ran == ["read-a"]
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "hello" in out


def test_an_entrys_scope_and_allowlist_become_the_turns_caveats(
    tmp_project: Path, home: Path, capsys: object
) -> None:
    (tmp_project / "src" / "b.txt").write_text("other\n", encoding="utf-8")
    entries = (
        ScheduleEntry(
            name="scoped",
            when=Interval(60),
            prompt="read src/b.txt",
            mode="read-only",
            model="fake/test",
            scope=("paths=a.txt",),
        ),
    )
    state = FileState(tmp_project)
    tick(as_tick_entries(entries), state, NOW, runner_for(entries, tmp_project, home=home, env={}))
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "hello" not in out  # a.txt's content never came back: b.txt was refused
