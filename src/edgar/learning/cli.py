"""`edgar stats` and `edgar history show|distill` [MEM-19, MEM-17]."""

# These two commands live inside the removable package rather than beside the
# other inspection commands in cli/inspect.py, and that is not a preference: a
# module in cli/ that imported edgar.learning would break tier isolation and fail
# tests/unit/test_architecture.py [NFR-12]. cli/main.py reaches this module by
# name with importlib, the same way cli/setup.py reaches attach(), so deleting
# the folder removes the commands and nothing else.
#
#   edgar stats              what the runs add up to
#   edgar history show       the entries, as written; pending, never facts
#   edgar history distill    the entries -> pending facts for `memory review`

from __future__ import annotations

import sys
import time
from pathlib import Path

from edgar.learning.experience import Experience
from edgar.learning.history import distill, entries
from edgar.memory.store import Memory, project_scope

USAGE = "usage: edgar stats | edgar history show|distill"


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    root = cwd.resolve()
    if argv == ["stats"]:
        return _stats(root)
    if argv == ["history", "show"]:
        return _show(root)
    if argv == ["history", "distill"]:
        return _distill(root, home or Path.home())
    print(USAGE, file=sys.stderr)
    return 2


def _stats(root: Path) -> int:
    # One block, in the order a person asks the questions [MEM-19].
    stats = Experience(root / ".edgar" / "learning.db").stats()
    if not stats.runs:
        print("no runs recorded yet")
        return 0
    since = time.strftime("%Y-%m-%d", time.localtime(stats.since))
    verdicts = ", ".join(f"{count} {name}" for name, count in sorted(stats.verification.items()))
    print(f"runs       {stats.runs} since {since}")
    print(f"verified   {verdicts}")
    print(f"failures   {stats.with_failures} runs had a failing tool call")
    print(f"cost       ${stats.cost:.4f}")
    print(f"tools      {_tally(stats.tools)}")
    print(f"shapes     {_tally(stats.shapes)}")
    return 0


def _show(root: Path) -> int:
    found = entries(root / ".edgar" / "history.md")
    if not found:
        print("no history yet; it is written unless --no-history or [memory] history = false")
        return 0
    print("\n\n".join(found))
    return 0


def _distill(root: Path, home: Path) -> int:
    memory = Memory(home / ".edgar" / "memory.db")
    facts = distill(root / ".edgar" / "history.md", memory, project_scope(root))
    if not facts:
        print("nothing recurs often enough to propose")
        return 0
    # Said plainly, because it is the point: these are proposals, not facts.
    print(f"{len(facts)} proposed, none active; confirm with `edgar memory review` [MEM-17]")
    for fact in facts:
        print(f"  {fact.id}  {fact.text}")
    return 0


def _tally(counts: list[tuple[str, int]]) -> str:
    return ", ".join(f"{name} {count}" for name, count in counts) or "none"
