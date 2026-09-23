# When and due(): pure. No I/O, no clock read — the caller passes `now` [SCH-4].
# 1. parse_when() turns a schedule entry's string into a Cron or an Interval.
# 2. Cron matches a minute-truncated datetime field by field (POSIX-style).
# 3. due() returns every occurrence strictly after `last` and up to `now`, so a
#    caller asleep for a while sees the whole backlog and decides what to do
#    with it (schedule/tick.py owns that decision, not this module).

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from edgar.core.errors import ConfigError

# A gap this long is treated as "too long to replay minute by minute": due()
# stops at this many occurrences and returns what it found, oldest first.
MAX_OCCURRENCES = 500

_SHORTHAND = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}
_EVERY = re.compile(r"^every (\d+)(s|m|h)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}


@dataclass(frozen=True, slots=True)
class Interval:
    seconds: int


@dataclass(frozen=True, slots=True)
class Cron:
    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]  # POSIX: 0 and 7 both mean Sunday, normalised to 0

    def matches(self, at: datetime) -> bool:
        posix_weekday = (at.weekday() + 1) % 7  # datetime: Monday=0; POSIX: Sunday=0
        return (
            at.minute in self.minute
            and at.hour in self.hour
            and at.day in self.day
            and at.month in self.month
            and posix_weekday in self.weekday
        )


When = Cron | Interval


def parse_when(text: str) -> When:
    # 1. `every Ns|Nm|Nh` is an interval, in seconds.
    every = _EVERY.match(text.strip())
    if every:
        return Interval(int(every.group(1)) * _UNIT_SECONDS[every.group(2)])
    # 2. A shorthand expands to its five-field form.
    fields = _SHORTHAND.get(text.strip(), text.strip()).split()
    if len(fields) != 5:
        raise ConfigError(f"schedule: {text!r} is not a cron expression or `every N`")
    zipped = zip(fields, _RANGES, strict=True)
    minute, hour, day, month, weekday = (_field(f, lo, hi) for f, (lo, hi) in zipped)
    return Cron(minute, hour, day, month, weekday)


_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _field(text: str, lo: int, hi: int) -> frozenset[int]:
    # A field is a comma list of `*`, `N`, `A-B`, or either with a `/step`.
    values: set[int] = set()
    for part in text.split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            start, stop = lo, hi
        elif "-" in base:
            start, stop = (int(x) for x in base.split("-"))
        else:
            start = stop = int(base)
        values.update(v % 7 if hi == 7 else v for v in range(start, stop + 1, step))
    return frozenset(values)


def due(when: When, last: datetime | None, now: datetime) -> list[datetime]:
    # No prior run: due exactly once, now — a fresh entry does not replay history.
    if last is None:
        return [now]
    if isinstance(when, Interval):
        elapsed = (now - last).total_seconds()
        return [now] if elapsed >= when.seconds else []
    return _occurrences(when, last, now)


def _occurrences(when: Cron, last: datetime, now: datetime) -> list[datetime]:
    at = last.replace(second=0, microsecond=0) + timedelta(minutes=1)
    found: list[datetime] = []
    while at <= now and len(found) < MAX_OCCURRENCES:
        if when.matches(at):
            found.append(at)
        at += timedelta(minutes=1)
    return found
