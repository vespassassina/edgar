"""A scripted provider: no network, deterministic [ADR-0009 layer 1].

Tests hand it a script of responses. With no script, the `test` model follows a
few fixed rules so the CLI can be exercised end to end without a real model:

- a user message `read PATH` calls `read` with that path; `ls [PATH]` calls `ls`
- after tool results, it replies with the result text
- anything else is echoed back
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from edgar.context.tokens import approx_message_tokens, approx_tokens
from edgar.core.errors import ProviderError
from edgar.core.events import EventBus, TextDelta, ThinkingDelta
from edgar.core.message import ContentBlock, Message, TextBlock, ThinkingBlock, ToolUseBlock
from edgar.providers.base import Capabilities, ProviderResponse, Usage

if TYPE_CHECKING:
    from edgar.tools.base import ToolSchema

CAPABILITIES = Capabilities(
    tools=True,
    parallel_tool_calls=True,
    streaming=True,
    reasoning=True,
    prompt_caching=False,
    max_context=200_000,
    max_output=32_000,
)

_COMMAND = re.compile(r"^\s*(read|ls)(?:\s+(\S+))?\s*$")


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


class FakeProvider:
    name = "fake"
    family = "fake"
    capabilities = CAPABILITIES

    def __init__(self, script: Sequence[ScriptedResponse] | None = None) -> None:
        self.script = list(script) if script is not None else None
        self.requests: list[list[Message]] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,
    ) -> ProviderResponse:
        self.requests.append(list(messages))
        step = self._next(messages, model)
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
        message = Message("assistant", tuple(content))
        usage = step.usage or Usage(
            input_tokens=self.count_tokens(messages),
            output_tokens=approx_tokens(step.text),
            approximate=True,
        )
        stop = "tool_use" if step.tool_calls else "end_turn"
        return ProviderResponse(message, usage, stop, cost=0.0)  # it runs nowhere

    async def models(self) -> list[str]:
        return ["test"]

    def count_tokens(self, messages: Sequence[Message]) -> int:
        return approx_message_tokens(messages)

    def _next(self, messages: Sequence[Message], model: str) -> ScriptedResponse:
        if self.script is not None:
            if not self.script:
                raise ProviderError("fake provider script exhausted", hint="add responses")
            return self.script.pop(0)
        if model != "test":
            raise ProviderError(f"the fake provider has no model {model!r}", hint="use fake/test")
        return _rules(messages)


def _rules(messages: Sequence[Message]) -> ScriptedResponse:
    last = messages[-1]
    if last.role == "tool":
        return ScriptedResponse(text="\n".join(r.text for r in last.tool_results))
    match = _COMMAND.match(last.text)
    if match is None or (match[1] == "read" and match[2] is None):
        return ScriptedResponse(text=f"fake/test heard: {last.text}")
    calls_so_far = sum(len(m.tool_calls) for m in messages)
    call = ToolUseBlock(f"tu_{calls_so_far + 1}", match[1], {"path": match[2] or "."})
    return ScriptedResponse(tool_calls=[call])


def _chunks(text: str, n: int) -> list[str]:
    size = max(1, -(-len(text) // max(1, n)))
    return [text[i : i + size] for i in range(0, len(text), size)]


def make() -> FakeProvider:
    return FakeProvider()
