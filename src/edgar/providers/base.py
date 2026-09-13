"""The Provider port [ADR-0022]. Adapters translate; they never decide [ADR-0002]."""

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

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
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
    ) -> ProviderResponse: ...

    def count_tokens(self, messages: Sequence[Message]) -> int: ...
