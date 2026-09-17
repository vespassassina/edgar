"""The Anthropic Messages API, streamed [PRV-2].

Different enough from Chat Completions to earn its own adapter:

    system        → a top-level `system` field, marked for the prompt cache [PRV-8]
    assistant     → content blocks: thinking (signed), text, tool_use
    tool results  → a user message of tool_result blocks; a /steer after them
                    joins the same message, results first, since roles alternate
    images        → an image block with the bytes inline, base64, in a user
                    message or inside a tool result [ADR-0052]
    reasoning     → replayed only when it came from this family, with its
                    signature; anything else is dropped and announced [PRV-13]
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from edgar.core.errors import ProviderError
from edgar.core.events import EventBus, ReasoningDropped, TextDelta, ThinkingDelta
from edgar.core.message import (
    ContentBlock,
    ImageBlock,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from edgar.providers.base import ProviderResponse, Usage
from edgar.providers.http import HttpAdapter, encoded, events, tool_calls

if TYPE_CHECKING:
    from edgar.tools.base import ToolSchema

FAMILY = "anthropic"
VERSION = "2023-06-01"
_CACHE = {"type": "ephemeral"}


class Anthropic(HttpAdapter):
    family = FAMILY
    caching = True

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,
    ) -> ProviderResponse:
        system = "\n\n".join(m.text for m in messages if m.role == "system")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": self.capabilities.max_output,
            "messages": self._messages(messages, bus),
            "stream": True,
        }
        if system:
            body["system"] = [{"type": "text", "text": system, "cache_control": _CACHE}]
        if tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
        budget = self.quirks.thinking_budget
        if budget and reasoning:
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}

        blocks: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        stop = "end_turn"
        async with self.post(f"{self.base}/v1/messages", body, self._headers(), bus) as response:
            async for kind, data in events(response):
                if kind == "error" or data.get("type") == "error":
                    error = data.get("error") or {}
                    raise ProviderError(
                        f"{self.name}: {error.get('type', 'error')}: {error.get('message', data)}",
                        hint="the stream failed part way; send the prompt again",
                    )
                if kind == "message_start":
                    usage |= data["message"].get("usage") or {}
                elif kind == "content_block_start":
                    blocks[data["index"]] = dict(data["content_block"], json="")
                elif kind == "content_block_delta":
                    _delta(blocks[data["index"]], data["delta"], bus)
                elif kind == "message_delta":
                    stop = data.get("delta", {}).get("stop_reason") or stop
                    usage |= data.get("usage") or {}

        ordered = [blocks[i] for i in sorted(blocks)]
        text = "".join(b.get("text", "") for b in ordered if b["type"] == "text")
        raw = [(b["id"], b["name"], b["json"]) for b in ordered if b["type"] == "tool_use"]
        calls, rest, repairs = tool_calls(raw, text, [t.name for t in tools], native=True, bus=bus)
        origin = f"{FAMILY}:{model}"
        content: list[ContentBlock] = []
        for b in ordered:
            if b["type"] == "thinking":
                content.append(ThinkingBlock(b.get("thinking", ""), origin, b.get("signature")))
            elif b["type"] == "redacted_thinking":
                content.append(ThinkingBlock("", origin, redacted=b.get("data")))
        if rest:
            content.append(TextBlock(rest))
        content.extend(calls)
        read = int(usage.get("cache_read_input_tokens") or 0)
        write = int(usage.get("cache_creation_input_tokens") or 0)
        counted = Usage(
            input_tokens=int(usage.get("input_tokens") or 0) + read + write,
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=read,
            cache_write_tokens=write,
            repairs=repairs,
        )
        self.observe(messages, counted)
        stop = "tool_use" if calls else stop
        message = Message("assistant", tuple(content))
        return ProviderResponse(message, counted, stop, cost=self.cost(model, counted))

    def listing(self) -> tuple[str, dict[str, str]] | None:
        return f"{self.base}/v1/models", self._headers()

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key or "", "anthropic-version": VERSION}

    def _messages(self, messages: Sequence[Message], bus: EventBus) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        dropped: set[str] = set()
        for m in messages:
            if m.role == "system":
                continue
            blocks: list[dict[str, Any]] = []
            for b in m.content:
                if isinstance(b, ThinkingBlock):
                    if b.family != FAMILY:
                        dropped.add(b.origin)
                    elif b.redacted is not None:
                        blocks.append({"type": "redacted_thinking", "data": b.redacted})
                    elif b.signature is not None:
                        blocks.append(
                            {"type": "thinking", "thinking": b.text, "signature": b.signature}
                        )
                elif isinstance(b, TextBlock):
                    if b.text:
                        blocks.append({"type": "text", "text": b.text})
                elif isinstance(b, ToolUseBlock):
                    blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.args})
                elif isinstance(b, ImageBlock):
                    blocks.append(_image(b))
                else:
                    result: dict[str, Any] = {"type": "tool_result", "tool_use_id": b.tool_use_id}
                    # Messages takes text and images inside a tool result, in order.
                    # Without images the content stays the plain string it has always
                    # been, so a result with no picture goes out unchanged.
                    if b.images:
                        parts: list[dict[str, Any]] = [{"type": "text", "text": b.text or "…"}]
                        result["content"] = parts + [_image(i) for i in b.images]
                    elif b.text:
                        result["content"] = b.text
                    if b.is_error:
                        result["is_error"] = True
                    blocks.append(result)
            role = "assistant" if m.role == "assistant" else "user"
            if out and out[-1]["role"] == role:  # roles must alternate: merge, in order
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": blocks or [{"type": "text", "text": "…"}]})
        if out and out[-1]["content"]:
            # The second cache breakpoint moves with the conversation, so each request
            # in a turn reads the previous one's prefix from the cache [PRV-8].
            out[-1]["content"][-1] = dict(out[-1]["content"][-1], cache_control=_CACHE)
        for origin in sorted(dropped):
            bus.emit(ReasoningDropped(from_origin=origin, to_family=FAMILY))
        return out


def _image(block: ImageBlock) -> dict[str, Any]:
    # Messages takes the bytes inline, base64, with the media type beside them.
    source = {"type": "base64", "media_type": block.media_type, "data": encoded(block)}
    return {"type": "image", "source": source}


def _delta(block: dict[str, Any], delta: Mapping[str, Any], bus: EventBus) -> None:
    kind = delta.get("type")
    if kind == "text_delta":
        block["text"] = block.get("text", "") + delta["text"]
        bus.emit(TextDelta(text=delta["text"]))
    elif kind == "thinking_delta":
        block["thinking"] = block.get("thinking", "") + delta["thinking"]
        bus.emit(ThinkingDelta(text=delta["thinking"]))
    elif kind == "signature_delta":
        block["signature"] = delta["signature"]
    elif kind == "input_json_delta":
        block["json"] += delta["partial_json"]


make = Anthropic  # the registry builds adapters through `make`
