"""Cron and interval parsing, and due() as a pure function of (when, last, now)
[SCH-4, SCH-5]. Every test passes explicit datetimes — nothing here reads the
clock."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from edgar.core.errors import ConfigError
from edgar.schedule.due import Cron, Interval, due, parse_when

# 2026-09-23 is a Wednesday.
WED = datetime(2026, 9, 23, 9, 30)


def cron(text: str) -> Cron:
    when = parse_when(text)
    assert isinstance(when, Cron)
    return when


def test_every_15m_parses_to_an_interval_in_seconds() -> None:
    assert parse_when("every 15m") == Interval(900)


def test_every_2h_and_every_30s_convert_their_unit() -> None:
    assert parse_when("every 2h") == Interval(7200)
    assert parse_when("every 30s") == Interval(30)


def test_hourly_shorthand_expands_to_the_top_of_every_hour() -> None:
    when = cron("@hourly")
    assert when.matches(datetime(2026, 9, 23, 14, 0))
    assert not when.matches(datetime(2026, 9, 23, 14, 1))


def test_weekly_shorthand_matches_only_sunday_midnight() -> None:
    when = cron("@weekly")
    assert when.matches(datetime(2026, 9, 27, 0, 0))  # a Sunday
    assert not when.matches(datetime(2026, 9, 23, 0, 0))  # a Wednesday


def test_a_five_field_cron_expression_matches_its_field() -> None:
    when = cron("30 9 * * 3")  # 09:30 on Wednesdays
    assert when.matches(WED)
    assert not when.matches(WED + timedelta(days=1))


def test_a_range_and_a_step_narrow_the_field() -> None:
    when = cron("0 9-17/2 * * *")
    assert when.matches(datetime(2026, 9, 23, 9, 0))
    assert when.matches(datetime(2026, 9, 23, 11, 0))
    assert not when.matches(datetime(2026, 9, 23, 10, 0))


def test_weekday_7_and_0_both_mean_sunday() -> None:
    sunday = datetime(2026, 9, 27, 0, 0)
    assert cron("0 0 * * 7").matches(sunday)
    assert cron("0 0 * * 0").matches(sunday)


def test_something_that_is_neither_cron_nor_every_is_rejected() -> None:
    with pytest.raises(ConfigError):
        parse_when("whenever")


def test_a_fresh_entry_with_no_last_run_is_due_exactly_once_at_now() -> None:
    when = parse_when("@daily")
    assert due(when, None, WED) == [WED]


def test_an_interval_is_due_once_elapsed_has_passed_it() -> None:
    when = Interval(600)
    last = WED
    assert due(when, last, last + timedelta(seconds=599)) == []
    assert due(when, last, last + timedelta(seconds=600)) == [last + timedelta(seconds=600)]


def test_a_cron_entry_returns_every_missed_minute_in_order() -> None:
    when = parse_when("@hourly")
    last = datetime(2026, 9, 23, 10, 5)
    now = datetime(2026, 9, 23, 13, 5)
    assert due(when, last, now) == [
        datetime(2026, 9, 23, 11, 0),
        datetime(2026, 9, 23, 12, 0),
        datetime(2026, 9, 23, 13, 0),
    ]


def test_no_occurrence_between_last_and_now_is_an_empty_list() -> None:
    when = parse_when("@daily")
    assert due(when, WED, WED + timedelta(minutes=1)) == []
