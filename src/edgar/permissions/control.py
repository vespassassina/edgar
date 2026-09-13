"""Control files: the files that steer edgar itself [PERM-12].

Writing or editing one is Ask in every mode but yolo. A model that could rewrite
its own instructions or config could widen its own policy, which only a human may
do (PERM-8, ADR-0021).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

_TREES = ("prompts", "agents", "tools", "extensions", "skills")
_FILES = ("config.toml", "personality.md", "schedules.toml")


def control_files(cwd: Path, home: Path, instructions: Iterable[str]) -> Callable[[Path], bool]:
    roots = [cwd / ".edgar", home / ".edgar"]
    files = {(root / name).resolve() for root in roots for name in _FILES}
    files |= {(cwd / name).resolve() for name in instructions}
    trees = [(root / tree).resolve() for root in roots for tree in _TREES]
    learned = [(root / "skills" / "learned").resolve() for root in roots]

    def is_control(path: Path) -> bool:
        if path in files:
            return True
        if any(path.is_relative_to(tree) for tree in learned):
            return False  # machine-owned by design (SKL-13)
        return any(path.is_relative_to(tree) for tree in trees)

    return is_control
