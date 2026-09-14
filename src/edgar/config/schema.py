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
    tools: dict[str, Literal["allow", "ask", "deny"]] = field(default_factory=dict)  # [PERM-2]


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


@dataclass(frozen=True, slots=True)
class ProviderSection:
    """One `[providers.NAME]` block [PRV-12]. A key left unset keeps the provider's
    own value from `providers/quirks.py`; a new NAME needs `kind` and `base_url`."""

    kind: Literal["openai-compatible", "anthropic"] | None = None
    base_url: str | None = None
    api_key_env: str | None = None  # the variable holding the key, never the key [CFG-6]
    api_key_command: list[str] | None = None  # argv printing a token; user config only [PRV-20]
    auth_style: Literal["bearer", "api-key", "none"] | None = None
    api_version: str | None = None  # Azure
    native_tools: bool | None = None  # false: tool calls travel as text [PRV-16]
    parallel_tools: bool | None = None
    stream_usage: bool | None = None
    max_context: int | None = None
    max_output: int | None = None
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] | None = None
    cost_source: Literal["table", "response", "free"] | None = None
    thinking_budget: int | None = None  # Anthropic extended thinking
    prompt_profile: Literal["auto", "full", "compact"] | None = None  # [PRV-17]


@dataclass(frozen=True, slots=True)
class PriceSection:
    """`[pricing."provider/model"]`, USD per million tokens [BUD-5]."""

    input: float
    output: float
    cache_read: float | None = None  # unset: billed as input
    cache_write: float | None = None


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

# Sections made of named blocks, `[providers.NAME]` and `[pricing."a/b"]`, each block
# validated against its dataclass.
TABLES: dict[str, type] = {"providers": ProviderSection, "pricing": PriceSection}

# Accepted now and validated by the milestone that first reads them, so a config
# written against the full spec loads today. Listed, not guessed: anything else
# unknown is an error.
LATER = frozenset(
    {
        "route",  # v1
        "model.fallback",  # v1
        "model.escalation",  # v2
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
    providers: dict[str, ProviderSection] = field(default_factory=dict)
    pricing: dict[str, PriceSection] = field(default_factory=dict)
    # Where each value came from: "default", a file path, "env EDGAR_…" or "flag --…"
    # [CFG-2].
    origins: dict[str, str] = field(default_factory=dict)
    later: dict[str, Any] = field(default_factory=dict)
