"""The Anthropic Messages API, streamed [PRV-2].

Different enough from Chat Completions to earn its own adapter:

    system        → a top-level `system` field, marked for the prompt cache [PRV-8]
    assistant     → content blocks: thinking (signed), text, tool_use
    tool results  → a user message of tool_result blocks; a /steer after them
                    joins the same message, results first, since roles alternate
    reasoning     → replayed only when it came from this family, with its
                    signature; anything else is dropped and announced [PRV-13]
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import httpx  # loaded only once a model names an Anthropic provider [PRV-4]

from edgar.config.schema import PriceSection, ProviderSection
from edgar.core.errors import ConfigError, ProviderError
from edgar.core.events import EventBus, ReasoningDropped, TextDelta, ThinkingDelta
from edgar.core.message import ContentBlock, Message, TextBlock, ThinkingBlock, ToolUseBlock
from edgar.providers.base import Capabilities, ProviderResponse, Usage
from edgar.providers.http import HttpAdapter, Retry, events, tool_calls
from edgar.providers.quirks import ANTHROPIC as DEFAULTS

if TYPE_CHECKING:
    from edgar.tools.base import ToolSchema

FAMILY = "anthropic"
VERSION = "2023-06-01"
_USED = {"kind", "base_url", "api_key_env", "max_context", "max_output", "thinking_budget"}
_USED |= {"prompt_profile"}
_CACHE = {"type": "ephemeral"}


class Anthropic(HttpAdapter):
    family = FAMILY

    def __init__(self, name: str, settings: ProviderSection, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.settings = settings
        self.capabilities = Capabilities(
            tools=True,
            parallel_tool_calls=True,
            streaming=True,
            reasoning=True,
            prompt_caching=True,
            max_context=settings.max_context or 200_000,
            max_output=settings.max_output or 16_384,
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
        budget = self.settings.thinking_budget
        if budget and reasoning:
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}

        blocks: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        stop = "end_turn"
        url = f"{(self.settings.base_url or '').rstrip('/')}/v1/messages"
        headers = {"x-api-key": self.api_key or "", "anthropic-version": VERSION}
        async with self.post(url, body, headers, bus) as response:
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
        url = f"{(self.settings.base_url or '').rstrip('/')}/v1/models"
        return url, {"x-api-key": self.api_key or "", "anthropic-version": VERSION}

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
                else:
                    result: dict[str, Any] = {"type": "tool_result", "tool_use_id": b.tool_use_id}
                    if b.text:
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


def make(
    name: str,
    block: ProviderSection | None,
    *,
    env: Mapping[str, str],
    prices: Mapping[str, PriceSection],
    transport: httpx.AsyncBaseTransport | None = None,
    retry: Retry | None = None,
) -> Anthropic:
    stated = {f.name for f in dataclasses.fields(ProviderSection)}
    unused = {k for k in stated - _USED if block is not None and getattr(block, k) is not None}
    if unused:
        raise ConfigError(
            f"[providers.{name}] sets {', '.join(sorted(unused))}, which the Anthropic "
            "adapter does not use",
            hint="those keys are for OpenAI-compatible servers; remove them",
        )
    settings = DEFAULTS if block is None else _over(DEFAULTS, block)
    if name != "anthropic" and (block is None or block.base_url is None):
        raise ConfigError(f"[providers.{name}] needs base_url")
    key = env.get(settings.api_key_env or "")
    if not key:
        raise ConfigError(
            f"{name}: the API key variable {settings.api_key_env} is not set",
            hint=f"export {settings.api_key_env}=… (keys live in the environment, never in config)",
        )
    return Anthropic(name, settings, api_key=key, prices=prices, transport=transport, retry=retry)


def _over(base: ProviderSection, block: ProviderSection) -> ProviderSection:
    stated = {k: v for k, v in dataclasses.asdict(block).items() if v is not None}
    return dataclasses.replace(base, **stated)
