"""Prompt assembly, most stable first [CTX-1].

The prefix is the system prompt, the personality and the instruction files, read
once at session start and joined into one system message whose bytes never change
until the session ends, so the provider's prompt cache holds (CTX-17). Tool schemas
travel beside the messages, in the request. After the cache breakpoint come the
rolling summary, the transcript and the current turn. Pinned facts and the skill
index join the prefix in later milestones, in the order BLUEPRINT §8.1 fixes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from edgar.core.message import Message, TextBlock
from edgar.core.session import Session

PERSONALITY_WARN = 500  # tokens [CTX-19]


@dataclass(frozen=True, slots=True)
class Section:
    name: str  # "personality" or an instruction file's name
    text: str
    source: Path


def pinned(root: Path, home: Path, instructions: list[str]) -> list[Section]:
    """What follows the system prompt above the cache breakpoint. All of it is
    control files (PERM-12): a model cannot rewrite its own instructions unasked."""
    sections = []
    # The project's personality replaces the user's; they never merge [ADR-0030].
    for path in (root / ".edgar" / "personality.md", home / ".edgar" / "personality.md"):
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            intro = "The user's preferences for tone and style:"
            sections.append(Section("personality", f"{intro}\n\n{text}", path))
            break
    for name in instructions:  # project scope, then user scope [CTX-15]
        for path in (root / name, home / ".edgar" / name):
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                sections.append(Section(name, f"Instructions from {path}:\n\n{text}", path))
    return sections


def system_text(system_prompt: str, pinned: list[Section]) -> str:
    """The one system message, joined once per session: the prefix's bytes [CTX-17]."""
    return "\n\n---\n\n".join([system_prompt, *(s.text for s in pinned)])


def build(session: Session, system_prompt: str) -> list[Message]:
    return [Message("system", (TextBlock(system_prompt),)), *session.transcript]
