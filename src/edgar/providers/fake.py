"""`fake/test`: a model that runs nowhere, for trying edgar without a key.

It follows three fixed rules, deterministic and offline:

- a user message `read PATH` calls `read` with that path; `ls [PATH]` calls `ls`
- after tool results, it replies with the result text
- anything else is echoed back

Tests script it further (`tests/support/scripted.py`) [ADR-0009 layer 1].
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from edgar.context.tokens import approx_message_tokens, approx_tokens
from edgar.core.errors import ProviderError
from edgar.core.events import EventBus, TextDelta
from edgar.core.message import Message, TextBlock, ToolUseBlock
from edgar.providers.base import Capabilities, ProviderResponse, Usage

if TYPE_CHECKING:
    from edgar.tools.base import ToolSchema

_COMMAND = re.compile(r"^\s*(read|ls)(?:\s+(\S+))?\s*$")


class FakeProvider:
    name = "fake"
    family = "fake"
    capabilities = Capabilities(
        tools=True,
        parallel_tool_calls=True,
        streaming=True,
        reasoning=True,
        prompt_caching=False,
        images=True,  # it round-trips an ImageBlock, which is what the tests need
        max_context=200_000,
        max_output=32_000,
    )

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,
    ) -> ProviderResponse:
        if model != "test":
            raise ProviderError(f"the fake provider has no model {model!r}", hint="use fake/test")
        text, call = _rules(messages)
        if text:
            bus.emit(TextDelta(text=text))
        message = Message("assistant", (call,) if call else (TextBlock(text),))
        usage = Usage(self.count_tokens(messages), approx_tokens(text), approximate=True)
        return ProviderResponse(message, usage, "tool_use" if call else "end_turn", cost=0.0)

    async def models(self) -> list[str]:
        return ["test"]

    def count_tokens(self, messages: Sequence[Message]) -> int:
        return approx_message_tokens(messages)


def _rules(messages: Sequence[Message]) -> tuple[str, ToolUseBlock | None]:
    last = messages[-1]
    if last.role == "tool":
        return "\n".join(r.text for r in last.tool_results), None
    match = _COMMAND.match(last.text)
    if match is None or (match[1] == "read" and match[2] is None):
        return f"fake/test heard: {last.text}", None
    calls_so_far = sum(len(m.tool_calls) for m in messages)
    return "", ToolUseBlock(f"tu_{calls_so_far + 1}", match[1], {"path": match[2] or "."})


def make() -> FakeProvider:
    return FakeProvider()
