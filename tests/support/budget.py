"""Size budgets from AGENTS.md and NFR-4, counted the same way everywhere.

Every "lines" budget in edgar means lines of code (ADR-0040). A line of code is a
non-blank line that is not only a comment. Docstrings count: they are text a
reader has to get through. Comments are free, so explaining code never costs
budget. Run directly for a report (``just loc``); ``tests/unit/test_size_budget.py``
fails the build when a budget is exceeded.
"""

# What this measures:
#   for each tier: every .py file under src/edgar, in lines of code
#   core/:         the core package alone, capped at 2,000
#   v2 tier only:  everything but the v2 packages must still fit v1's budget
#   core/loop.py:  the loop alone, capped at 200

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "edgar"

# The tier being built. Moves to "v1" when M7 starts and "v2" when M12 starts; the
# numbers themselves never move (ADR-0015).
TARGET_TIER = "core"
TIER_BUDGETS = {"core": 5_000, "v1": 8_000, "v2": 11_000}

# Where v2 lives. Nothing outside these may import them (NFR-12).
V2_PATHS = ("learning", "controller", "schedule", "broker", "providers/escalation.py")


@dataclass(frozen=True, slots=True)
class Limit:
    label: str
    loc: int
    budget: int

    @property
    def ok(self) -> bool:
        return self.loc <= self.budget


def count_loc(path: Path) -> int:
    # Keep a line when it has something on it and that something is not a comment.
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def _is_v2(path: Path, root: Path) -> bool:
    # "learning/x.py" is v2 because it sits under "learning"; so is the one file
    # "providers/escalation.py" itself.
    rel = path.relative_to(root).as_posix()
    return any(rel == p or rel.startswith(p + "/") for p in V2_PATHS)


def limits(root: Path = SRC, tier: str = TARGET_TIER) -> list[Limit]:
    # 1. Count every file once.
    files = sorted(root.rglob("*.py"))
    total = sum(count_loc(f) for f in files)
    without_v2 = sum(count_loc(f) for f in files if not _is_v2(f, root))
    core = sum(count_loc(f) for f in files if f.relative_to(root).parts[0] == "core")
    # 2. Compare each total with its budget.
    result = [
        Limit(f"src/ total ({tier} tier)", total, TIER_BUDGETS[tier]),
        Limit("core/", core, 2_000),
    ]
    if tier == "v2":
        result.append(Limit("src/ without v2 packages", without_v2, TIER_BUDGETS["v1"]))
    # 3. The loop, in lines of code like everything else: its comments are free.
    loop = root / "core" / "loop.py"
    if loop.exists():
        result.append(Limit("core/loop.py", count_loc(loop), 200))
    return result


def report() -> int:
    # One line per limit; exit 1 if any is over.
    worst = 0
    for limit in limits():
        mark = "ok " if limit.ok else "OVER"
        share = limit.loc / limit.budget
        print(f"{mark}  {limit.label:<30} {limit.loc:>6} / {limit.budget:<6} {share:>5.0%}")
        worst = worst if limit.ok else 1
    return worst


if __name__ == "__main__":
    sys.exit(report())
