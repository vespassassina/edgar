"""Size budgets from AGENTS.md and NFR-4, counted the same way everywhere.

A line of code is a non-blank line that is not only a comment. Docstrings count:
they are text a reader has to get through. Run directly for a report
(``just loc``); ``tests/unit/test_size_budget.py`` fails the build when a budget
is exceeded.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "edgar"

# The tier being built. Moves to "v1" when M7 starts and "v2" when M12 starts; the
# numbers themselves never move (ADR-0015).
TARGET_TIER = "core"
TIER_BUDGETS = {"core": 5_000, "v1": 8_000, "v2": 11_000}

V2_PATHS = ("learning", "controller", "schedule", "providers/escalation.py")


@dataclass(frozen=True, slots=True)
class Limit:
    label: str
    loc: int
    budget: int

    @property
    def ok(self) -> bool:
        return self.loc <= self.budget


def count_loc(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def _is_v2(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(rel == p or rel.startswith(p + "/") for p in V2_PATHS)


def limits(root: Path = SRC, tier: str = TARGET_TIER) -> list[Limit]:
    files = sorted(root.rglob("*.py"))
    total = sum(count_loc(f) for f in files)
    without_v2 = sum(count_loc(f) for f in files if not _is_v2(f, root))
    core = sum(count_loc(f) for f in files if f.relative_to(root).parts[0] == "core")
    loop = root / "core" / "loop.py"
    result = [
        Limit(f"src/ total ({tier} tier)", total, TIER_BUDGETS[tier]),
        Limit("core/", core, 2_000),
    ]
    if tier == "v2":
        result.append(Limit("src/ without v2 packages", without_v2, TIER_BUDGETS["v1"]))
    if loop.exists():
        # loop.py is budgeted in physical lines, not LOC: the point is that it fits
        # on a couple of screens.
        loop_lines = len(loop.read_text(encoding="utf-8").splitlines())
        result.append(Limit("core/loop.py (lines)", loop_lines, 200))
    return result


def report() -> int:
    worst = 0
    for limit in limits():
        mark = "ok " if limit.ok else "OVER"
        share = limit.loc / limit.budget
        print(f"{mark}  {limit.label:<30} {limit.loc:>6} / {limit.budget:<6} {share:>5.0%}")
        worst = worst if limit.ok else 1
    return worst


if __name__ == "__main__":
    sys.exit(report())
