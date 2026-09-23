"""tick(): due() plus the catch-up policy plus overlap prevention [SCH-6,
SCH-7]. State is a tiny in-memory fake here; test_schedule_state.py covers the
real file-backed one."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from edgar.core.errors import ConfigError
from edgar.schedule.due import Interval
from edgar.schedule.tick import Entry, catch_up, tick

NOW = datetime(2026, 9, 23, 13, 0)


class FakeState:
    def __init__(self) -> None:
        self.last: dict[str, datetime] = {}
        self.locked: set[str] = set()

    def last_run(self, name: str) -> datetime | None:
        return self.last.get(name)

    def set_last_run(self, name: str, at: datetime) -> None:
        self.last[name] = at

    def try_lock(self, name: str) -> bool:
        if name in self.locked:
            return False
        self.locked.add(name)
        return True

    def unlock(self, name: str) -> None:
        self.locked.discard(name)


@pytest.mark.parametrize(
    ("policy", "expected_count"),
    [("skip", 0), ("once", 1), ("all", 3)],
)
def test_catch_up_policy_decides_how_many_missed_occurrences_run(
    policy: str, expected_count: int
) -> None:
    occurrences = [NOW - timedelta(hours=n) for n in (2, 1, 0)]
    assert len(catch_up(policy, occurrences)) == expected_count


def test_catch_up_with_nothing_missed_is_always_empty() -> None:
    assert catch_up("all", []) == []


def test_an_unknown_catch_up_policy_is_rejected() -> None:
    with pytest.raises(ConfigError):
        catch_up("eventually", [NOW])


def test_a_new_entry_runs_once_and_a_ran_name_is_reported() -> None:
    entry = Entry(name="nightly", when=Interval(60))
    calls: list[datetime] = []
    ran = tick([entry], FakeState(), NOW, lambda e, at: calls.append(at))
    assert ran == ["nightly"]
    assert calls == [NOW]


def test_nothing_due_advances_last_run_but_calls_no_runner() -> None:
    entry = Entry(name="hourly", when=Interval(3600))
    state = FakeState()
    state.set_last_run("hourly", NOW)
    ran = tick(
        [entry], state, NOW + timedelta(minutes=1), lambda e, at: pytest.fail("must not run")
    )
    assert ran == []
    assert state.last_run("hourly") == NOW + timedelta(minutes=1)


def test_a_still_running_entry_is_skipped_and_its_last_run_untouched() -> None:
    entry = Entry(name="slow", when=Interval(60))
    state = FakeState()
    state.locked.add("slow")
    ran = tick([entry], state, NOW, lambda e, at: pytest.fail("must not run"))
    assert ran == []
    assert state.last_run("slow") is None


def test_the_lock_is_released_even_when_the_runner_raises() -> None:
    entry = Entry(name="flaky", when=Interval(60))
    state = FakeState()

    def boom(e: Entry, at: datetime) -> None:
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        tick([entry], state, NOW, boom)
    assert "flaky" not in state.locked


def test_a_skip_policy_drops_the_backlog_and_still_advances_last_run() -> None:
    entry = Entry(name="daily", when=Interval(86400), catch_up="skip")
    state = FakeState()
    state.set_last_run("daily", NOW - timedelta(days=3))
    ran = tick([entry], state, NOW, lambda e, at: pytest.fail("skip must not run"))
    assert ran == []
    assert state.last_run("daily") == NOW
