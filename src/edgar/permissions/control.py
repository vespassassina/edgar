"""Control files: the files that steer edgar itself [PERM-12].

Writing or editing one is Ask in every mode but yolo. A model that could rewrite
its own instructions or config could widen its own policy, which only a human may
do (PERM-8, ADR-0021).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from pathlib import Path

_TREES = ("prompts", "agents", "tools", "extensions", "skills")
_FILES = ("config.toml", "personality.md", "schedules.toml")


def control_files(cwd: Path, home: Path, instructions: Iterable[str]) -> Callable[[Path], bool]:
    roots = [cwd / ".edgar", home / ".edgar"]
    files = {(root / name).resolve() for root in roots for name in _FILES}
    files |= {(base / name).resolve() for base in (cwd, home / ".edgar") for name in instructions}
    trees = [(root / tree).resolve() for root in roots for tree in _TREES]
    learned = [(root / "skills" / "learned").resolve() for root in roots]

    def is_control(path: Path) -> bool:
        if path in files:
            return True
        if any(path.is_relative_to(tree) for tree in learned):
            return False  # machine-owned by design (SKL-13)
        if any(path.is_relative_to(tree) for tree in trees):
            return True
        # The same answer for an `.edgar/` anywhere else, so a subagent's git
        # worktree under `.edgar/worktrees/` cannot hold a second, unguarded copy
        # of the files that steer edgar [SUB-11]. Only ever adds an Ask.
        parts = path.parts
        at = max((i for i, part in enumerate(parts) if part == ".edgar"), default=-1)
        rest = parts[at + 1 :] if at >= 0 else ()
        return bool(rest) and (rest[0] in _FILES or (len(rest) > 1 and rest[0] in _TREES))

    return is_control


def snapshot(cwd: Path, home: Path, instructions: Iterable[str]) -> dict[str, str]:
    """Each control file's digest. Compared at session end, it names the files that
    changed while the session ran, for the next session to warn about [PERM-12]."""
    roots = [cwd / ".edgar", home / ".edgar"]
    paths = [root / name for root in roots for name in _FILES]
    paths += [base / name for base in (cwd, home / ".edgar") for name in instructions]
    for root in roots:
        learned = root / "skills" / "learned"  # machine-owned (SKL-13)
        for tree in _TREES:
            paths += [p for p in (root / tree).rglob("*") if not p.is_relative_to(learned)]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
