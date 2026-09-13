"""The system prompt is a file [CTX-16, ADR-0023].

The shipped `prompts/system.md` is used unless the project has its own
`.edgar/prompts/system.md`, which is a control file: hand-authored, and the model
cannot change it without asking (PERM-12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SHIPPED = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True, slots=True)
class Prompt:
    text: str
    source: Path


def load_prompt(cwd: Path, name: str = "system") -> Prompt:
    override = cwd / ".edgar" / "prompts" / f"{name}.md"
    source = override if override.is_file() else SHIPPED / f"{name}.md"
    return Prompt(source.read_text(encoding="utf-8"), source)
