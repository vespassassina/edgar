"""The one message vocabulary. Nothing outside providers/ sees a provider-native shape.

Frozen and slotted, with tuples rather than lists: compaction builds new transcripts
instead of mutating old ones, which makes it idempotent, and immutable values make
property testing straightforward [CTX-8].
"""

# How a conversation looks in these types. A transcript is a list of Messages; each
# Message has a role and a tuple of blocks:
#
#   Message("user",      [TextBlock("fix the failing test")])
#   Message("assistant", [ThinkingBlock(...), TextBlock("Let me look."),
#                         ToolUseBlock(id="t1", name="read", args={"path": "x.py"})])
#   Message("tool",      [ToolResultBlock(tool_use_id="t1", content=[TextBlock("…")])])
#   Message("assistant", [TextBlock("Fixed: the import was wrong.")])
#
# The rule everything depends on: an assistant message with tool calls is followed
# by exactly one tool message holding one result per call, matched by id
# (core/units.py checks it) [CTX-4].
#
# Each provider adapter translates these to and from its own JSON; nothing else in
# edgar ever sees that JSON.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Who a message comes from. "tool" carries tool results back to the model.
Role = Literal["system", "user", "assistant", "tool"]

# Why a tool call failed, as the harness classified it. The learning path sees only
# this, never the error text itself [MEM-22].
ErrorKind = Literal[
    "validation",  # the arguments did not match the tool's schema
    "permission_denied",  # the permission engine or the user said no
    "timeout",
    "not_found",  # no tool by that name
    "nonzero_exit",  # a command ran and failed
    "provider_http",
    "cancelled",  # the turn was cancelled while the call was open
    "internal",  # the tool itself raised: a bug in the tool, not in the call
]


@dataclass(frozen=True, slots=True)
class TextBlock:
    # Plain text: what the human typed, or what the model said.
    text: str
    attached: bool = False  # stdin or @file: context, never a learning source [CLI-3]


@dataclass(frozen=True, slots=True)
class ThinkingBlock:
    # The model's reasoning, when the provider returns it. Replayed only to the
    # same family of model that wrote it; dropped for any other [PRV-13].
    text: str
    origin: str  # adapter family + model, e.g. "anthropic:claude-sonnet-5" [PRV-13]
    signature: str | None = None  # Anthropic verifies this on replay
    redacted: str | None = None  # opaque encrypted reasoning, replayed as given

    @property
    def family(self) -> str:
        # "anthropic:claude-sonnet-5" -> "anthropic"
        return self.origin.partition(":")[0]


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    # The model asking to run a tool. `id` pairs it with its result.
    id: str
    name: str
    args: dict[str, Any]
    # The raw arguments when they were not a JSON object even after repair. The
    # pipeline returns this to the model as a validation error [PRV-16, TOOL-2].
    malformed: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """Computed by the harness, never parsed from tool text [MEM-22]."""

    # Small and structured on purpose: the only facts about a failure that are
    # safe to learn from, because the harness wrote them, not the tool.
    tool: str
    kind: ErrorKind
    exit_code: int | None = None
    program: str | None = None  # argv[0] basename, [A-Za-z0-9._-] only


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    # What a tool call produced, success or failure. Failures are results too: the
    # model sees them and can try something else [§17].
    tool_use_id: str  # must match a ToolUseBlock.id in the preceding message
    content: tuple[TextBlock, ...]
    is_error: bool = False
    truncated: bool = False  # the output was cut; the rest is in `blob`
    untrusted: bool = False  # network-sourced: sets session taint [TOOL-13]
    error: ErrorRecord | None = None  # set when is_error, by the harness
    blob: str | None = None  # path of the spilled full output [CTX-13]

    @property
    def text(self) -> str:
        return "".join(block.text for block in self.content)


# Any block a message can hold.
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True)
class Message:
    # One entry in the transcript.
    role: Role
    content: tuple[ContentBlock, ...]
    pinned: bool = False  # never compacted [CTX-5]
    meta: dict[str, Any] = field(default_factory=dict)  # e.g. via="verify" for feedback

    @classmethod
    def user(cls, text: str, **meta: Any) -> Message:
        # Shorthand for a one-block user message.
        return cls("user", (TextBlock(text),), meta=meta)

    # Views over the blocks, so callers never loop over content themselves.

    @property
    def text(self) -> str:
        # All the text blocks joined: what the model "said".
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_calls(self) -> tuple[ToolUseBlock, ...]:
        # What the model asked to run, in order. Empty means it is done.
        return tuple(b for b in self.content if isinstance(b, ToolUseBlock))

    @property
    def tool_results(self) -> tuple[ToolResultBlock, ...]:
        return tuple(b for b in self.content if isinstance(b, ToolResultBlock))
