"""Deterministic skill activation: a typed word, or a path the previous round
touched, loads a skill's body without the model asking for it [SKL-17]. The
same match feeds VER-1's skill-verify source: a loaded skill's own `verify:`
command, tried once nothing higher in the precedence order claims it.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence

from edgar.core.message import Message
from edgar.skills.discovery import Skill, split


def matching(skills: dict[str, Skill], prompt: str, touched: tuple[str, ...]) -> list[Skill]:
    """A skill matches if a typed word is one of its keywords, or a touched path
    matches one of its globs; in discovery order, so callers can rely on it."""
    words = {w.lower() for w in prompt.split()}
    return [
        s
        for s in skills.values()
        if words & set(s.keywords) or any(fnmatch.fnmatch(t, p) for t in touched for p in s.paths)
    ]


def activate(skills: dict[str, Skill], prompt: str, touched: tuple[str, ...]) -> list[str]:
    return bodies(matching(skills, prompt, touched))


def bodies(hits: Sequence[Skill]) -> list[str]:
    # Each match's body, the same text the `skill` tool would have loaded.
    return [f"skill {s.name}:\n{_body(s)}" for s in hits]


def verify_command(hits: Sequence[Skill]) -> str | None:
    """VER-1's "if the only sources are loaded skills, each of their commands
    runs, in load order": chained into one shell command, first failure wins."""
    commands = [s.verify for s in hits if s.verify]
    return " && ".join(commands) if commands else None


def _body(skill: Skill) -> str:
    _, body = split(skill.path.read_text(encoding="utf-8"))
    return body.strip()


def touched_paths(transcript: Sequence[Message]) -> tuple[str, ...]:
    """Every `path` argument the most recent round of tool calls carried, read
    between turns so it never touches the pairing invariant [CTX-4]."""
    calls = next((m.tool_calls for m in reversed(transcript) if m.tool_calls), ())
    return tuple(str(p) for c in calls if isinstance(p := c.args.get("path"), str))
