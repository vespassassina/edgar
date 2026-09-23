# 1. Caveat: one narrowing rule, a plain frozen value with no behaviour of its
#    own -- `authorize.py` is the only place that reads what it means.
# 2. parse_scope() turns human-typed "KEY=VALUE" pairs into caveats, resolving
#    a relative `until=` duration to an absolute instant right away, so a
#    ticket's expiry never depends on when someone later checks it.
# 3. Repeating the same key (tools=, paths=, hosts=) widens that list; `until`
#    and `calls` replace, since "expire sooner" or "allow fewer" is what a
#    second `--scope until=...` most plausibly means.

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from edgar.core.errors import ConfigError

Kind = Literal["tools", "paths", "hosts", "calls", "until"]
KINDS: tuple[Kind, ...] = ("tools", "paths", "hosts", "calls", "until")
_DURATION = re.compile(r"^(\d+)(s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


@dataclass(frozen=True, slots=True)
class Caveat:
    kind: Kind
    value: str


def parse_scope(pairs: Iterable[str], *, now: datetime | None = None) -> tuple[Caveat, ...]:
    now = now or datetime.now(UTC)
    values: dict[Kind, str] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise ConfigError(f"--scope wants KEY=VALUE, got {pair!r}")
        if key not in KINDS:
            raise ConfigError(f"unknown --scope caveat {key!r} (one of {', '.join(KINDS)})")
        kind: Kind = key
        value = _resolve_until(raw.strip(), now) if kind == "until" else raw.strip()
        if kind in values and kind not in ("until", "calls"):
            values[kind] = f"{values[kind]},{value}"
        else:
            values[kind] = value
    return tuple(Caveat(kind=k, value=v) for k, v in values.items())


def _resolve_until(value: str, now: datetime) -> str:
    match = _DURATION.match(value)
    if not match:
        raise ConfigError(f"until= wants a duration like 10m, 1h or 30s: got {value!r}")
    n, unit = int(match[1]), match[2]
    return (now + timedelta(seconds=n * _UNIT_SECONDS[unit])).isoformat()
