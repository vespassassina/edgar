"""FileState: the on-disk half of tick.py's State protocol [SCH-6]."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from edgar.schedule.state import FileState


def test_last_run_is_none_until_something_sets_it(tmp_path: Path) -> None:
    state = FileState(tmp_path)
    assert state.last_run("nightly") is None


def test_last_run_round_trips_through_the_json_file(tmp_path: Path) -> None:
    state = FileState(tmp_path)
    at = datetime(2026, 9, 23, 9, 0)
    state.set_last_run("nightly", at)
    assert FileState(tmp_path).last_run("nightly") == at


def test_setting_one_entrys_last_run_does_not_disturb_another(tmp_path: Path) -> None:
    state = FileState(tmp_path)
    state.set_last_run("a", datetime(2026, 9, 23, 9, 0))
    state.set_last_run("b", datetime(2026, 9, 23, 10, 0))
    assert state.last_run("a") == datetime(2026, 9, 23, 9, 0)
    assert state.last_run("b") == datetime(2026, 9, 23, 10, 0)


def test_try_lock_succeeds_once_and_fails_while_held(tmp_path: Path) -> None:
    state = FileState(tmp_path)
    assert state.try_lock("nightly") is True
    assert state.try_lock("nightly") is False  # a second process racing for the same lock


def test_unlock_then_try_lock_succeeds_again(tmp_path: Path) -> None:
    state = FileState(tmp_path)
    state.try_lock("nightly")
    state.unlock("nightly")
    assert state.try_lock("nightly") is True


def test_unlocking_something_never_locked_does_not_raise(tmp_path: Path) -> None:
    FileState(tmp_path).unlock("never-ran")
