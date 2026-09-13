"""The Provider port [ADR-0022]. Adapters translate; they never decide [ADR-0002].

Cancellation is asyncio's own: cancelling the task that awaits `stream()` closes
the HTTP response, and an adapter must not swallow the CancelledError.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from edgar.core.message import Message

if TYPE_CHECKING:
    from edgar.core.events import EventBus
    from edgar.tools.base import ToolSchema


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    approximate: bool = False  # the provider reported none; counted by edgar [PRV-6]
    repairs: int = 0  # tool calls fixed by repair.py [PRV-16]

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            self.approximate or other.approximate,
            self.repairs + other.repairs,
        )


@dataclass(frozen=True, slots=True)
class Capabilities:
    tools: bool
    parallel_tool_calls: bool
    streaming: bool
    reasoning: bool
    prompt_caching: bool
    max_context: int
    max_output: int


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    message: Message  # role "assistant", canonical blocks only
    usage: Usage
    stop_reason: str
    cost: float | None = None  # USD; None is "unknown pricing", never a wrong zero [BUD-5]


class Provider(Protocol):
    name: str
    family: str  # "openai-compatible" | "anthropic" | plugin-defined
    capabilities: Capabilities

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,  # False after a mid-turn family switch [PRV-13]
    ) -> ProviderResponse: ...

    def count_tokens(self, messages: Sequence[Message]) -> int: ...

    async def models(self) -> list[str]:
        """The provider's own list of model names, for the picker [CLI-30]. Only
        ever called when the user asks; empty when the provider has no list."""
        ...
