"""The system prompt is a file [CTX-16, ADR-0023].

The shipped `prompts/system.md` is used unless the project has its own
`.edgar/prompts/system.md`, which is a control file: hand-authored, and the model
cannot change it without asking (PERM-12). Small models get `prompts/compact.md`,
overridable the same way [PRV-17].
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SHIPPED = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True, slots=True)
class Prompt:
    text: str
    source: Path


def load_prompt(cwd: Path, name: str = "system") -> Prompt:
    override = cwd / ".edgar" / "prompts" / f"{name}.md"
    source = override if override.is_file() else SHIPPED / f"{name}.md"
    return Prompt(source.read_text(encoding="utf-8"), source)


COMPACT_BELOW = 32_000  # tokens of context [PRV-17]


def choose_profile(setting: str, max_context: int) -> Literal["full", "compact"]:
    """`auto` picks `compact` for models with under 32k tokens of context, whose
    window a full prompt and every tool schema would crowd [PRV-17]."""
    if setting == "full":
        return "full"
    if setting == "compact":
        return "compact"
    return "compact" if max_context < COMPACT_BELOW else "full"


def profile_prompt(profile: Literal["full", "compact"]) -> str:
    return "system" if profile == "full" else "compact"
