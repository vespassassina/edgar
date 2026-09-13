"""The config model (BLUEPRINT §14). The dataclasses are the schema.

Each field's type hint is the validation rule and its default is the default, so
there is one place to read what a key accepts. Validation is hand-written in
`load.py` rather than delegated to a library, which keeps it off the startup path
and lets every message name the file, the key and the expected type [CFG-3].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Mode = Literal["read-only", "ask", "auto", "yolo"]


@dataclass(frozen=True, slots=True)
class ModelSection:
    default: str | None = None
    # Auxiliary roles default to the main model, never to one the user did not
    # name [PRV-15].
    compactor: str | None = None
    controller: str | None = None
    condenser: str | None = None


@dataclass(frozen=True, slots=True)
class PermissionsSection:
    mode: Mode = "ask"
    write_paths: list[str] = field(default_factory=lambda: ["./**"])
    shell_allow: list[str] = field(default_factory=list)
    shell_deny: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolsSection:
    max_output_tokens: int = 8000  # spill threshold [TOOL-4]
    schema_budget: int = 4000  # [TOOL-15]


@dataclass(frozen=True, slots=True)
class PromptSection:
    profile: Literal["auto", "full", "compact"] = "auto"  # [PRV-17]


@dataclass(frozen=True, slots=True)
class VerifySection:
    command: str | None = None
    max_attempts: int = 2


@dataclass(frozen=True, slots=True)
class BudgetSection:
    turn_cost_cap: float | None = None
    session_cost_cap: float | None = None
    daily_cost_cap: float | None = None


@dataclass(frozen=True, slots=True)
class ContextSection:
    autocompact: bool = True
    compact_at: float = 0.70
    compact_to: float = 0.50
    keep_last_turns: int = 4


@dataclass(frozen=True, slots=True)
class InstructionsSection:
    files: list[str] = field(default_factory=lambda: ["AGENTS.md"])  # [CTX-15]


@dataclass(frozen=True, slots=True)
class ShellSection:
    program: str = "auto"  # [TOOL-11]
    sandbox: Literal["none", "bwrap", "seatbelt", "container"] = "none"  # [PERM-15]


SECTIONS: dict[str, type] = {
    "model": ModelSection,
    "permissions": PermissionsSection,
    "tools": ToolsSection,
    "prompt": PromptSection,
    "verify": VerifySection,
    "budget": BudgetSection,
    "context": ContextSection,
    "instructions": InstructionsSection,
    "shell": ShellSection,
}

# Accepted now and validated by the milestone that first reads them, so a config
# written against the full spec loads today. Listed, not guessed: anything else
# unknown is an error.
LATER = frozenset(
    {
        "providers",  # M2
        "route",  # v1
        "model.fallback",  # v1
        "model.escalation",  # v2
        "permissions.tools",  # M3
        "memory",  # v1
        "subagents",  # v1
        "extensions",  # v1
        "hooks",  # v1
        "mcp",  # v1
        "browser",  # v1, the /browser MCP preset
        "controller",  # v2
        "history",  # v2
    }
)


@dataclass(frozen=True, slots=True)
class Config:
    model: ModelSection = field(default_factory=ModelSection)
    permissions: PermissionsSection = field(default_factory=PermissionsSection)
    tools: ToolsSection = field(default_factory=ToolsSection)
    prompt: PromptSection = field(default_factory=PromptSection)
    verify: VerifySection = field(default_factory=VerifySection)
    budget: BudgetSection = field(default_factory=BudgetSection)
    context: ContextSection = field(default_factory=ContextSection)
    instructions: InstructionsSection = field(default_factory=InstructionsSection)
    shell: ShellSection = field(default_factory=ShellSection)
    # Where each value came from: "default", a file path, "env EDGAR_…" or "flag --…"
    # [CFG-2].
    origins: dict[str, str] = field(default_factory=dict)
    later: dict[str, Any] = field(default_factory=dict)
