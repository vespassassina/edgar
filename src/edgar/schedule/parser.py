# parser.py: schedules.toml -> tuple[ScheduleEntry, ...], validated once at load
# time so a bad entry fails before any tick runs [SCH-1, SCH-8].
# 1. Read the file if it exists; no file means no entries, not an error.
# 2. Each [[entries]] table becomes one ScheduleEntry: parse_when() rejects a bad
#    `when`, and `mode`/`catch_up` are checked against their closed sets.
# 3. `edgar schedule add` (schedule/cli.py) only ever appends a new [[entries]]
#    block to this same file; it never rewrites what is already there [SCH-1].

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from edgar.config.schema import Mode
from edgar.core.errors import ConfigError
from edgar.schedule.due import When, parse_when

CATCH_UP_POLICIES = ("skip", "once", "all")


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    name: str
    when: When
    prompt: str
    mode: Mode = "read-only"
    agent: str | None = None
    model: str | None = None
    allowlist: tuple[str, ...] = ()
    verify: str | None = None
    catch_up: str = "once"
    scope: tuple[str, ...] = ()  # KEY=VALUE caveats, the same shape as --scope [CAP-4]


def path(cwd: Path) -> Path:
    return cwd / ".edgar" / "schedules.toml"


def load(cwd: Path) -> tuple[ScheduleEntry, ...]:
    file = path(cwd)
    if not file.exists():
        return ()
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"schedules.toml: {exc}") from exc
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ConfigError("schedules.toml: `entries` must be an array of tables")
    return tuple(_entry(raw) for raw in entries)


def append(cwd: Path, raw: dict[str, object]) -> ScheduleEntry:
    """Validate `raw` and add it to schedules.toml as a new [[entries]] block,
    without touching anything already in the file [SCH-1]."""
    entry = _entry(raw)  # fails before anything is written
    file = path(cwd)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("a", encoding="utf-8") as f:
        f.write(render(raw))
    return entry


def render(raw: dict[str, object]) -> str:
    lines = ["\n[[entries]]\n"]
    for key in ("name", "when", "prompt", "mode", "agent", "model", "verify", "catch_up"):
        if raw.get(key):
            lines.append(f"{key} = {json.dumps(raw[key])}\n")
    allowlist = raw.get("allowlist")
    if isinstance(allowlist, list | tuple) and allowlist:
        lines.append(f"allowlist = {json.dumps(list(allowlist))}\n")
    scope = raw.get("scope")
    if isinstance(scope, dict) and scope:
        lines.append("\n[entries.scope]\n")
        lines += [f"{k} = {json.dumps(v)}\n" for k, v in scope.items()]
    return "".join(lines)


def remove(cwd: Path, name: str) -> bool:
    """Drop the entry named `name`, rewriting the file. Unlike append(), this
    is an explicit rewrite the human asked for, not a silent one."""
    file = path(cwd)
    if not file.exists():
        return False
    data = tomllib.loads(file.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    remaining = [e for e in entries if e.get("name") != name]
    if len(remaining) == len(entries):
        return False
    file.write_text("".join(render(e) for e in remaining), encoding="utf-8")
    return True


def _entry(raw: dict[str, object]) -> ScheduleEntry:
    name = _required(raw, "name")
    mode = _required(raw, "mode", default="read-only")
    if mode not in get_args(Mode):
        raise ConfigError(f"schedules.toml: entry {name!r} has mode {mode!r}, not {get_args(Mode)}")
    catch_up = _required(raw, "catch_up", default="once")
    if catch_up not in CATCH_UP_POLICIES:
        raise ConfigError(
            f"schedules.toml: entry {name!r} has catch_up {catch_up!r}, not {CATCH_UP_POLICIES}"
        )
    scope_table = raw.get("scope", {})
    if not isinstance(scope_table, dict):
        raise ConfigError(f"schedules.toml: entry {name!r} has a scope that is not a table")
    return ScheduleEntry(
        name=name,
        when=parse_when(_required(raw, "when")),
        prompt=_required(raw, "prompt"),
        mode=mode,  # type: ignore[arg-type]  # narrowed by the get_args() check above
        agent=_optional(raw, "agent"),
        model=_optional(raw, "model"),
        allowlist=_strings(raw, "allowlist"),
        verify=_optional(raw, "verify"),
        catch_up=catch_up,
        scope=tuple(f"{k}={v}" for k, v in scope_table.items()),
    )


def _required(raw: dict[str, object], key: str, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"schedules.toml: every entry needs a non-empty {key!r}")
    return value


def _optional(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def _strings(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key, ())
    return tuple(value) if isinstance(value, list | tuple) else ()
