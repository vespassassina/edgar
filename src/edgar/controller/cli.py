"""`edgar controller log|apply|revert` [CTRL-7, CTRL-10]."""

# Inside the removable package for the same reason learning/cli.py is: a module
# under cli/ that imported edgar.controller would break tier isolation and fail
# tests/unit/test_architecture.py [NFR-12]. cli/main.py reaches this one by name
# with importlib, so deleting the folder removes the commands and nothing else.
#
#   edgar controller log         what it did, what it would have done, what it was
#                                refused. Newest first
#   edgar controller apply ID    turn one dry run into the real thing, by hand
#   edgar controller revert ID   take one applied row back out
#
# There is no `edgar controller run`. Nothing here starts a controller call: the
# gate is the only thing that does, and a threshold is the only thing that asks it
# to [CTRL-2].

from __future__ import annotations

import sys
import time
from pathlib import Path

from edgar.controller.apply import approve, revert
from edgar.controller.store import Controls

USAGE = "usage: edgar controller log | edgar controller apply ID | edgar controller revert ID"


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    root = cwd.resolve()
    if argv == ["controller", "log"]:
        return _log(Controls(root / ".edgar" / "controller.db"))
    if len(argv) == 3 and argv[1] in ("apply", "revert"):
        return _one(Controls(root / ".edgar" / "controller.db"), argv[1], argv[2])
    print(USAGE, file=sys.stderr)
    return 2


def _log(store: Controls) -> int:
    # 1. The mutations, in the order a person reads a log in. The id is first
    #    because the id is what the other two commands take.
    rows = store.mutations()
    rejected = store.rejections()
    if not rows and not rejected:
        print("the controller has not done anything; it is off unless [controller] enabled = true")
        return 0
    for row in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(row.at))
        print(f"{row.id:>4}  {when}  {row.state:<8} {row.action:<19} {row.detail}")
        if row.reason:
            print(f"      because: {row.reason}")
    # 2. Then what it asked for and did not get. A controller refused every turn is
    #    a configuration problem, and this is where you would see it [CTRL-8].
    for _, at, _, problem in rejected:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(at))
        print(f"   -  {when}  refused   {problem}")
    return 0


def _one(store: Controls, verb: str, raw: str) -> int:
    if not raw.isdigit():
        print(f"{raw!r} is not a mutation id; `edgar controller log` lists them", file=sys.stderr)
        return 2
    answer = approve(store, int(raw)) if verb == "apply" else revert(store, int(raw))
    print(answer)
    # "no mutation 7" is a usage error, not a thing that happened.
    return 2 if answer.startswith("no mutation") else 0
