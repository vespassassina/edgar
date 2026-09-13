"""Turning a tool call into something a rule can match [PERM-3, PERM-4, PERM-5, PERM-14].

Paths are resolved before anything is compared: `resolve()` collapses `..` and
follows symlinks, so a path is judged by where it lands, not by how it is spelled.
On Windows it also expands 8.3 short names, and a UNC path never lands inside the
working directory. This is the one place that touches the file system for a
decision; `decide()` gets the result.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Credentials: never readable or writable by the model outside yolo.
CREDENTIALS = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".netrc", ".config/gcloud")
_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_SUBSTITUTION = re.compile(r"\$\(|`|<\(|>\(")
CATASTROPHIC = ("rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/*", "mkfs*", ":(){*")


@dataclass(frozen=True, slots=True)
class Subject:
    """What a decision is about: a resolved path, a command line, or a URL."""

    text: str  # shown in prompts, events and grants
    path: Path | None = None
    command: str | None = None


def subject(args: dict[str, Any], cwd: Path) -> Subject:
    """For built-ins; command and HTTP tools describe their own subject."""
    if isinstance(args.get("command"), str):
        return Subject(args["command"], command=args["command"])
    if isinstance(args.get("url"), str):
        return Subject(args["url"])
    raw = args.get("path", ".")
    path = (cwd / str(raw)).resolve()
    return Subject(str(path), path=path)


def segments(command: str) -> list[str]:
    """`a && b | c` → ["a", "b", "c"], whitespace normalised."""
    return [" ".join(part.split()) for part in _SPLIT.split(command) if part.strip()]


def substitutes(command: str) -> bool:
    return bool(_SUBSTITUTION.search(command))


def matches(segment: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(segment, p) for p in patterns)


def inside(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def within(path: Path, cwd: Path, globs: Iterable[str]) -> bool:
    """`write_paths` globs are relative to the working directory; `**` spans folders."""
    text = path.as_posix()
    for pattern in globs:
        full = (cwd / pattern).as_posix() if not Path(pattern).is_absolute() else pattern
        if fnmatch.fnmatchcase(text, full.replace("/./", "/").replace("**", "*")):
            return True
    return False


def credential(path: Path, home: Path) -> bool:
    return any(inside(path, home / name) for name in CREDENTIALS)
