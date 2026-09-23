# `edgar schedule list|add NAME|remove NAME|run NAME`, `edgar tick`,
# `edgar install-tick`/`uninstall-tick` [SCH-2, SCH-3, SCH-12]. Reached from
# cli/main.py by name, the same lazy-import seam as broker and controller
# [ADR-0015, NFR-12].
#
# 1. `tick`/`install-tick`/`uninstall-tick` are their own top-level verbs.
# 2. Everything else is `edgar schedule <verb> ...`: list, add, remove, run.
# 3. `add` parses `--flag value` pairs into a raw dict and hands it to
#    parser.append(), which validates before writing anything [SCH-1].

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from edgar.schedule import install as host
from edgar.schedule.parser import ScheduleEntry, append, load, path, remove
from edgar.schedule.run import as_tick_entries, runner_for
from edgar.schedule.state import FileState
from edgar.schedule.store import SelfSchedules
from edgar.schedule.tick import Entry, tick

USAGE = (
    "usage: edgar schedule list | add NAME --when EXPR --prompt TEXT [--mode M] "
    "[--agent A] [--model M] [--allowlist a,b] [--verify CMD] [--catch-up P] "
    "[--scope KEY=VALUE]... | remove NAME | run NAME\n"
    "       edgar tick [--now ISO] | install-tick | uninstall-tick"
)


def command(argv: list[str], cwd: Path) -> int:
    if argv[:1] == ["tick"]:
        return _tick(argv[1:], cwd)
    if argv[:1] == ["install-tick"]:
        print(host.install(cwd))
        return 0
    if argv[:1] == ["uninstall-tick"]:
        print(host.uninstall(cwd))
        return 0
    verb, rest = (argv[1], argv[2:]) if len(argv) > 1 else ("list", [])
    if verb == "list" and not rest:
        return _list(cwd)
    if verb == "add" and rest:
        return _add(rest, cwd)
    if verb == "remove" and len(rest) == 1:
        return _remove(rest[0], cwd)
    if verb == "run" and len(rest) == 1:
        return _run(rest[0], cwd)
    print(USAGE, file=sys.stderr)
    return 2


def _list(cwd: Path) -> int:
    entries, selves = load(cwd), SelfSchedules(cwd / ".edgar" / "edgar.db").list()
    if not entries and not selves:
        print(f"no entries in {path(cwd)}; `edgar schedule add` to create one")
        return 0
    for e in entries:
        print(f"{e.name}: {e.when} mode={e.mode} catch_up={e.catch_up}")
    for s in selves:
        print(f"{s.entry.name} [self]: {s.entry.when} mode={s.entry.mode} depth={s.depth}")
    return 0


def _add(args: list[str], cwd: Path) -> int:
    raw: dict[str, object] = {"name": args[0]}
    scope: dict[str, str] = {}
    i = 1
    while i < len(args):
        flag, value, i = args[i], args[i + 1], i + 2
        if flag == "--scope":
            key, _, val = value.partition("=")
            scope[key] = val
            raw["scope"] = scope
        elif flag == "--allowlist":
            raw["allowlist"] = value.split(",")
        elif flag == "--catch-up":
            raw["catch_up"] = value
        elif flag.startswith("--"):
            raw[flag[2:]] = value
        else:
            print(USAGE, file=sys.stderr)
            return 2
    entry = append(cwd, raw)
    print(f"added {entry.name!r} to {path(cwd)}")
    return 0


def _remove(name: str, cwd: Path) -> int:
    if not remove(cwd, name):
        print(f"no entry named {name!r}", file=sys.stderr)
        return 1
    print(f"removed {name!r}")
    return 0


def _all_entries(cwd: Path) -> tuple[tuple[ScheduleEntry, ...], dict[str, int]]:
    # schedules.toml plus self_schedules, as one tuple tick.py/run.py can run
    # without knowing which table an entry came from; `depths` names only the
    # self-scheduled ones [SCH-11].
    selves = SelfSchedules(cwd / ".edgar" / "edgar.db").list()
    entries = load(cwd) + tuple(s.entry for s in selves)
    return entries, {s.entry.name: s.depth for s in selves}


def _run(name: str, cwd: Path) -> int:
    entries, depths = _all_entries(cwd)
    matches = [e for e in entries if e.name == name]
    if not matches:
        print(f"no entry named {name!r}", file=sys.stderr)
        return 1
    runner = runner_for(entries, cwd, depths=depths)
    runner(Entry(name=name, when=matches[0].when), datetime.now())
    return 0


def _tick(args: list[str], cwd: Path) -> int:
    now = datetime.fromisoformat(args[1]) if args[:1] == ["--now"] else datetime.now()
    entries, depths = _all_entries(cwd)
    ran = tick(
        as_tick_entries(entries), FileState(cwd), now, runner_for(entries, cwd, depths=depths)
    )
    print(f"ran: {', '.join(ran)}" if ran else "nothing due")
    return 0
