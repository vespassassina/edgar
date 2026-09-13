"""The one message vocabulary. Nothing outside providers/ sees a provider-native shape.

Frozen and slotted, with tuples rather than lists: compaction builds new transcripts
instead of mutating old ones, which makes it idempotent, and immutable values make
property testing straightforward [CTX-8].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]

ErrorKind = Literal[
    "validation",
    "permission_denied",
    "timeout",
    "not_found",
    "nonzero_exit",
    "provider_http",
    "cancelled",
    "internal",  # the tool itself raised: a bug in the tool, not in the call
]


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    attached: bool = False  # stdin or @file: context, never a learning source [CLI-3]


@dataclass(frozen=True, slots=True)
class ThinkingBlock:
    text: str
    origin: str  # adapter family + model, e.g. "anthropic:claude-sonnet-5" [PRV-13]
    signature: str | None = None  # Anthropic verifies this on replay
    redacted: str | None = None  # opaque encrypted reasoning, replayed as given

    @property
    def family(self) -> str:
        return self.origin.partition(":")[0]


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    id: str
    name: str
    args: dict[str, Any]
    # The raw arguments when they were not a JSON object even after repair. The
    # pipeline returns this to the model as a validation error [PRV-16, TOOL-2].
    malformed: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """Computed by the harness, never parsed from tool text [MEM-22]."""

    tool: str
    kind: ErrorKind
    exit_code: int | None = None
    program: str | None = None  # argv[0] basename, [A-Za-z0-9._-] only


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    tool_use_id: str  # must match a ToolUseBlock.id in the preceding message
    content: tuple[TextBlock, ...]
    is_error: bool = False
    truncated: bool = False
    untrusted: bool = False  # network-sourced: sets session taint [TOOL-13]
    error: ErrorRecord | None = None
    blob: str | None = None  # path of the spilled full output [CTX-13]

    @property
    def text(self) -> str:
        return "".join(block.text for block in self.content)


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: tuple[ContentBlock, ...]
    pinned: bool = False  # never compacted [CTX-5]
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def user(cls, text: str, **meta: Any) -> Message:
        return cls("user", (TextBlock(text),), meta=meta)

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_calls(self) -> tuple[ToolUseBlock, ...]:
        return tuple(b for b in self.content if isinstance(b, ToolUseBlock))

    @property
    def tool_results(self) -> tuple[ToolResultBlock, ...]:
        return tuple(b for b in self.content if isinstance(b, ToolResultBlock))
