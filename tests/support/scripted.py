"""The fake provider, scripted: each request answers with the next step [ADR-0009 layer 1].

With no script it falls back to the `fake/test` rules. Steps can think, stream in
chunks, stall mid-stream, wait before answering, or raise, which is what the loop,
cancellation and REPL tests need.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from edgar.context.tokens import approx_tokens
from edgar.core.errors import ProviderError
from edgar.core.events import EventBus, TextDelta, ThinkingDelta
from edgar.core.message import ContentBlock, Message, TextBlock, ThinkingBlock, ToolUseBlock
from edgar.providers.base import ProviderResponse, Usage
from edgar.providers.fake import FakeProvider


@dataclass
class ScriptedResponse:
    text: str = ""
    thinking: str | None = None
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    usage: Usage | None = None  # None: approximate from the text
    raises: Exception | None = None
    delay_s: float = 0.0  # exercise cancellation
    stream_chunks: int = 1  # exercise partial-stream handling
    stall_s: float = 0.0  # pause after the first chunk: a stream to cut mid-generation


class ScriptedProvider(FakeProvider):
    def __init__(self, script: Sequence[ScriptedResponse] | None = None) -> None:
        self.script = list(script) if script is not None else None
        self.requests: list[list[Message]] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[Any],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,
    ) -> ProviderResponse:
        self.requests.append(list(messages))
        if self.script is None:
            return await super().stream(messages, tools, model=model, bus=bus, reasoning=reasoning)
        if not self.script:
            raise ProviderError("fake provider script exhausted", hint="add responses")
        step = self.script.pop(0)
        if step.delay_s:
            await asyncio.sleep(step.delay_s)
        if step.raises is not None:
            raise step.raises
        content: list[ContentBlock] = []
        if step.thinking is not None and reasoning:
            bus.emit(ThinkingDelta(text=step.thinking))
            content.append(ThinkingBlock(step.thinking, origin=f"fake:{model}"))
        if step.text:
            for n, chunk in enumerate(_chunks(step.text, step.stream_chunks)):
                bus.emit(TextDelta(text=chunk))
                if n == 0 and step.stall_s:
                    await asyncio.sleep(step.stall_s)
            content.append(TextBlock(step.text))
        content.extend(step.tool_calls)
        usage = step.usage or Usage(
            self.count_tokens(messages), approx_tokens(step.text), approximate=True
        )
        stop = "tool_use" if step.tool_calls else "end_turn"
        return ProviderResponse(Message("assistant", tuple(content)), usage, stop, cost=0.0)


def _chunks(text: str, n: int) -> list[str]:
    size = max(1, -(-len(text) // max(1, n)))
    return [text[i : i + size] for i in range(0, len(text), size)]
