"""The post-turn checks are deterministic and cost nothing [CTRL-1, CTRL-2]."""

from __future__ import annotations

import pytest

from edgar.config.schema import ControllerSection
from edgar.controller.triggers import CHECKS, Signals, summary, tripped

OFF = ControllerSection()


def test_an_ordinary_turn_trips_nothing() -> None:
    assert tripped(Signals(), OFF) == ()


@pytest.mark.parametrize(
    ("name", "signals"),
    [
        ("context", Signals(token_fraction=0.7)),
        ("errors", Signals(error_streak=3)),
        ("budget", Signals(burn_rate=0.9)),
        ("output", Signals(output_tokens=20_000)),
        ("slow", Signals(wall_clock_s=400.0)),
    ],
)
def test_each_check_trips_on_its_own_signal(name: str, signals: Signals) -> None:
    assert tripped(signals, OFF) == (name,)


def test_several_checks_trip_in_the_table_order() -> None:
    both = Signals(token_fraction=0.9, output_tokens=20_000)
    assert tripped(both, OFF) == ("context", "output")


def test_always_mode_trips_on_a_turn_where_nothing_happened() -> None:
    # The opt-in CTRL-2 names: every turn gets a look, and it says why.
    assert tripped(Signals(), ControllerSection(mode="always")) == ("always",)


def test_the_error_streak_check_is_off_when_its_threshold_is_zero() -> None:
    # Otherwise a zero threshold would trip on every turn, including a clean one.
    assert tripped(Signals(error_streak=0), ControllerSection(error_streak=0)) == ()


def test_the_summary_names_the_number_not_only_the_check() -> None:
    line = summary(Signals(error_streak=4), ("errors",))
    assert "4 turns in a row" in line


def test_every_check_has_a_line_in_the_summary() -> None:
    names = (*(name for name, _ in CHECKS), "always")
    assert "; ".join(summary(Signals(), (n,)) for n in names).count(";") == len(names) - 1
