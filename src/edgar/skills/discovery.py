"""Finding skills: `SKILL.md` folders, read for their frontmatter only [SKL-1..3]."""

# A skill is a folder holding a `SKILL.md`: YAML frontmatter with a `name` and a
# `description`, then a markdown body. Discovery reads only the frontmatter, so the
# prompt carries one line per skill; the body loads when the model calls the
# `skill` tool (tools/builtin/skill.py) [SKL-2, SKL-4]. A skill is instructions,
# never code that edgar runs.
#
# The flow:
#
#   for each scope, lowest priority first:
#       ~/.edgar/skills/learned, .edgar/skills/learned   (machine-written, v2)
#       ~/.edgar/skills, .edgar/skills                    (hand-authored)
#     for each <scope>/<folder>/SKILL.md, in name order:
#       read the frontmatter; if it is broken, note the problem and skip the file
#       if a skill by that name exists already, this one replaces it, with a warning
#
# So the project beats the user, and anything a human wrote beats anything learned,
# whatever its scope: a machine-written skill never shadows a human's.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FRONT = re.compile(r"---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)", re.S)
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # Claude's rule: lowercase, digits, hyphens


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str  # the one line the model sees until it loads the skill
    path: Path  # the SKILL.md; files beside it are the skill's resources [SKL-5]
    origin: str  # "user", "project", "user learned" or "project learned"


@dataclass
class Found:
    skills: dict[str, Skill] = field(default_factory=dict)  # by name, the winners
    problems: list[str] = field(default_factory=list)  # files skipped, and why
    warnings: list[str] = field(default_factory=list)  # a skill replaced by another


def split(text: str) -> tuple[dict[str, Any], str]:
    # The frontmatter as a dict, and the body after it; ValueError if it is broken.
    # PyYAML is imported only once a SKILL.md exists: a trivial run never pays for
    # it [NFR-1]. safe_load builds plain data, never objects [SKL-3].
    import yaml

    match = _FRONT.match(text)
    if match is None:
        raise ValueError("no frontmatter: the file must open with a --- block")
    try:
        head = yaml.safe_load(match[1])
    except yaml.YAMLError as exc:
        raise ValueError(f"the frontmatter is not YAML: {exc}") from None
    if not isinstance(head, dict):
        raise ValueError("the frontmatter must be a mapping of keys to values")
    return head, match[2]


def discover(root: Path, home: Path) -> Found:
    found = Found()
    # 1. Scopes, lowest priority first: each later one may replace an earlier one.
    scopes = [
        (home / ".edgar" / "skills" / "learned", "user learned"),
        (root / ".edgar" / "skills" / "learned", "project learned"),
        (home / ".edgar" / "skills", "user"),
        (root / ".edgar" / "skills", "project"),
    ]
    for folder, origin in scopes:
        for path in sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []:
            # 2. Read one skill; a broken file is reported, never fatal.
            try:
                skill = _read(path, origin)
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                found.problems.append(f"{path}: {exc}")
                continue
            # 3. Keep it, saying which one it replaces [TOOL-9].
            old = found.skills.get(skill.name)
            if old is not None:
                found.warnings.append(
                    f"the {origin} skill {skill.name!r} replaces the {old.origin} one"
                )
            found.skills[skill.name] = skill
    return found


def _read(path: Path, origin: str) -> Skill:
    head, _ = split(path.read_text(encoding="utf-8"))
    name, description = head.get("name"), head.get("description")
    if not isinstance(name, str) or not _NAME.match(name) or len(name) > 64:
        raise ValueError("`name` must be lowercase letters, digits and hyphens, up to 64")
    if name != path.parent.name:
        raise ValueError(f"`name` is {name!r} but the folder is {path.parent.name!r}")
    if not isinstance(description, str) or not 0 < len(description.strip()) <= 1024:
        raise ValueError("`description` must be text, 1 to 1,024 characters")
    return Skill(name, " ".join(description.split()), path, origin)
