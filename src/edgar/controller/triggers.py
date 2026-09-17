"""When is a turn worth a second opinion? Five deterministic checks [CTRL-1]."""

# The whole point of this file is that no model decides whether to call a model.
# The gate assembles five numbers about the turn that just ended, compares each
# with a threshold from `[controller]`, and only if one of them trips does a
# request go out [CTRL-2]. That ordering is what keeps the controller from being
# a per-turn tax on every session.
#
#   token_fraction   the turn's prompt tokens / the model's context window
#   error_streak     turns in a row that ended with a failing tool call
#   burn_rate        today's spend / daily_cost_cap; 0.0 when there is no cap
#   output_tokens    what the model wrote this turn
#   wall_clock_s     how long the turn took
#
# Everything here is pure, like `permissions.decide()` and `routing.select_model()`:
# the caller does the I/O and hands the results in, so the checks can be driven
# with any numbers at all and have no database, clock or provider of their own.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from edgar.config.schema import ControllerSection

Check = Callable[["Signals", ControllerSection], bool]


@dataclass(frozen=True, slots=True)
class Signals:
    """One turn, in the five numbers the checks compare. Assembled by
    `controller/gate.py` from the bus and the spend store, never read from here."""

    token_fraction: float = 0.0
    error_streak: int = 0
    burn_rate: float = 0.0
    output_tokens: int = 0
    wall_clock_s: float = 0.0


# Each check is (name, does it trip?). Kept as a table rather than a chain of ifs
# so `tripped()` reads as a list and a new check is one line, not a new branch.
CHECKS: tuple[tuple[str, Check], ...] = (
    ("context", lambda s, c: s.token_fraction >= c.token_fraction),
    ("errors", lambda s, c: c.error_streak > 0 and s.error_streak >= c.error_streak),
    ("budget", lambda s, c: s.burn_rate >= c.burn_rate),
    ("output", lambda s, c: s.output_tokens >= c.output_tokens),
    ("slow", lambda s, c: s.wall_clock_s >= c.wall_clock_s),
)


def tripped(signals: Signals, config: ControllerSection) -> tuple[str, ...]:
    """The checks this turn trips, in the fixed order above. Empty means the turn
    was ordinary and no request goes out [CTRL-2]."""
    # `always` is the opt-in that skips the question: every turn gets a look, and
    # the reason given is the mode itself rather than a check nobody failed.
    if config.mode == "always":
        return ("always",)
    return tuple(name for name, check in CHECKS if check(signals, config))


def summary(signals: Signals, names: tuple[str, ...]) -> str:
    """One line naming what tripped and with what number, for the outline the
    controller is given and for `edgar controller log`."""
    # The numbers matter as much as the names: "errors" alone does not tell the
    # controller whether two things failed or twenty.
    shown = {
        "context": f"context {signals.token_fraction:.0%} of the window",
        "errors": f"{signals.error_streak} turns in a row ended with a failing tool call",
        "budget": f"today's spend is {signals.burn_rate:.0%} of the daily cap",
        "output": f"{signals.output_tokens:,} output tokens in one turn",
        "slow": f"the turn took {signals.wall_clock_s:.0f} s",
        "always": "[controller] mode = always",
    }
    return "; ".join(shown[name] for name in names) or "nothing tripped"
