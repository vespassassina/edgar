"""One adapter for every OpenAI-compatible server [PRV-1, PRV-3, ADR-0002].

OpenAI, Azure, OpenRouter, Ollama and any `[providers.NAME]` block differ only in
the `Quirks` row they get; nothing below looks at a provider's name. The wire
format is Chat Completions, streamed:

    system        → {"role": "system", "content": "…"}
    user          → {"role": "user", "content": "…"}
    assistant     → {"role": "assistant", "content": "…", "tool_calls": [{id, function}]}
    tool results  → one {"role": "tool", "tool_call_id": …, "content": "…"} each
    images        → an image_url part with a data: URL, in a user message; a
                    picture a tool produced follows its result [ADR-0052]

Chat Completions has no standard field for sending reasoning back, so reasoning
this adapter received stays in the record and is not replayed; reasoning from
another family is dropped and announced [PRV-13].
"""

from __future__ import annotations

import json
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

FAMILY = "openai-compatible"

# For servers without native tool calls (native_tools = false): the tools travel in
# the system message and calls come back as text, parsed by repair.py [PRV-16].
TEXT_TOOLS = """

## Calling tools

This server has no native tool calls. To call a tool, reply with only a JSON
object, and nothing else: {"name": "TOOL", "arguments": {...}}. One call per reply.
The result comes back in the next message. The tools:
"""


class OpenAICompatible(HttpAdapter):
    family = FAMILY

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        model: str,
        bus: EventBus,
        reasoning: bool = True,
    ) -> ProviderResponse:
        q = self.quirks
        body: dict[str, Any] = {
            "model": model,
            "messages": self._messages(messages, tools, bus),
            "stream": True,
        }
        if tools and q.native_tools:
            body["tools"] = [_tool(t) for t in tools]
        if q.stream_usage:
            body["stream_options"] = {"include_usage": True}
        if q.max_tokens_param:
            body[q.max_tokens_param] = q.max_output

        text: list[str] = []
        thinking: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        stop = "end_turn"
        async with self.post(self._url(model), body, self._headers(), bus) as response:
            async for _, chunk in events(response):
                if chunk.get("error"):
                    raise ProviderError(f"{self.name}: {chunk['error']}")
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices") or ():  # Azure opens with no choices
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text.append(delta["content"])
                        bus.emit(TextDelta(text=delta["content"]))
                    said = delta.get("reasoning_content") or delta.get("reasoning")
                    if isinstance(said, str) and said:
                        thinking.append(said)
                        bus.emit(ThinkingDelta(text=said))
                    for n, part in enumerate(delta.get("tool_calls") or ()):
                        _merge(calls.setdefault(part.get("index", n), {}), part)
                    stop = _STOPS.get(choice.get("finish_reason"), stop)

        raw = [(c.get("id"), c.get("name", ""), c.get("arguments", "")) for c in calls.values()]
        names = [t.name for t in tools]
        blocks, rest, repairs = tool_calls(
            raw, "".join(text), names, native=q.native_tools, bus=bus
        )
        content: list[ContentBlock] = []
        if thinking:
            content.append(ThinkingBlock("".join(thinking), origin=f"{FAMILY}:{self.name}/{model}"))
        if rest:
            content.append(TextBlock(rest))
        content.extend(blocks)
        message = Message("assistant", tuple(content))
        counted = self._usage(usage, messages, message, repairs)
        self.observe(messages, counted)
        return ProviderResponse(
            message,
            counted,
            "tool_use" if blocks else stop,
            cost=self._cost(model, counted, usage.get("cost")),
        )

    def listing(self) -> tuple[str, dict[str, str]] | None:
        if self.quirks.api_version:  # Azure lists base models, not your deployments
            return None
        return f"{self.base}/models", self._headers()

    def _url(self, model: str) -> str:
        version = self.quirks.api_version
        if version:  # Azure: the model name is the deployment name
            return f"{self.base}/openai/deployments/{model}/chat/completions?api-version={version}"
        return f"{self.base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = dict(self.quirks.extra_headers or {})  # Copilot's, sent on every request
        style = self.quirks.auth_style
        if style == "none" or not self.api_key:
            return headers
        if style == "api-key":
            return {**headers, "api-key": self.api_key}
        return {**headers, "authorization": f"Bearer {self.api_key}"}

    def _messages(
        self, messages: Sequence[Message], tools: Sequence[ToolSchema], bus: EventBus
    ) -> list[dict[str, Any]]:
        native = self.quirks.native_tools
        out: list[dict[str, Any]] = []
        dropped: set[str] = set()
        for m in messages:
            if m.role == "system":
                extra = "" if native or not tools else TEXT_TOOLS + _describe(tools)
                out.append({"role": "system", "content": m.text + extra})
            elif m.role == "user":
                # Chat Completions takes a picture as one more part of a user
                # message's content, a data URL under image_url [ADR-0052].
                if m.images:
                    out.append({"role": "user", "content": _parts(m.text, m.images)})
                else:
                    _append(out, "user", m.text)
            elif m.role == "assistant":
                dropped |= {b.origin for b in m.content if isinstance(b, ThinkingBlock)}
                # Null content is allowed only beside tool calls.
                entry: dict[str, Any] = {"role": "assistant", "content": m.text or None}
                if not m.tool_calls:
                    entry["content"] = m.text
                if m.tool_calls and native:
                    entry["tool_calls"] = [_call(c) for c in m.tool_calls]
                elif m.tool_calls:
                    said = [json.dumps({"name": c.name, "arguments": c.args}) for c in m.tool_calls]
                    entry["content"] = "\n".join(filter(None, [m.text, *said]))
                out.append(entry)
            else:
                for r in m.tool_results:
                    if native:
                        out.append(
                            {"role": "tool", "tool_call_id": r.tool_use_id, "content": r.text}
                        )
                    else:
                        _append(out, "user", f"Tool result:\n{r.text}")
                # A `tool` message takes no picture in this wire format, so the ones a
                # call produced follow it as a user message, which is what OpenAI's
                # own guidance says to do. The pairing above it is untouched [CTX-4].
                shots = [i for r in m.tool_results for i in r.images]
                if shots:
                    out.append(
                        {"role": "user", "content": _parts("Images from that tool call:", shots)}
                    )
        for origin in sorted(o for o in dropped if not o.startswith(FAMILY + ":")):
            bus.emit(ReasoningDropped(from_origin=origin, to_family=FAMILY))
        return out

    def _usage(
        self, usage: Mapping[str, Any], sent: Sequence[Message], got: Message, repairs: int
    ) -> Usage:
        if not usage.get("prompt_tokens"):  # the server reported none: count it ourselves
            return Usage(
                input_tokens=self.count_tokens(sent),
                output_tokens=self.count_tokens([got]),
                approximate=True,
                repairs=repairs,
            )
        details = usage.get("prompt_tokens_details") or {}
        return Usage(
            input_tokens=int(usage["prompt_tokens"]),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cache_read_tokens=int(details.get("cached_tokens") or 0),
            repairs=repairs,
        )

    def _cost(self, model: str, usage: Usage, reported: Any) -> float | None:
        if self.quirks.cost_source == "free":
            return 0.0
        if self.quirks.cost_source == "response" and isinstance(reported, int | float):
            return float(reported)
        return self.cost(model, usage)


_STOPS = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


def _merge(slot: dict[str, Any], part: Mapping[str, Any]) -> None:
    """Fold one streamed piece of a tool call into what has arrived so far."""
    if part.get("id"):
        slot["id"] = part["id"]
    function = part.get("function") or {}
    if function.get("name") and not slot.get("name"):
        slot["name"] = function["name"]
    args = function.get("arguments")
    if isinstance(args, dict):  # some servers send the object rather than its text
        args = json.dumps(args)
    if args:
        slot["arguments"] = slot.get("arguments", "") + args


def _append(out: list[dict[str, Any]], role: str, text: str) -> None:
    if out and out[-1]["role"] == role and isinstance(out[-1]["content"], str):
        out[-1]["content"] += "\n\n" + text
    else:
        out.append({"role": role, "content": text})


def _parts(text: str, images: Sequence[ImageBlock]) -> list[dict[str, Any]]:
    # A content array: the text first, then one image_url part per picture.
    said = [{"type": "text", "text": text}] if text else []
    urls = [
        {"type": "image_url", "image_url": {"url": f"data:{i.media_type};base64,{encoded(i)}"}}
        for i in images
    ]
    return said + urls


def _call(c: ToolUseBlock) -> dict[str, Any]:
    # A malformed call goes back exactly as the model sent it, so it can see its slip.
    args = c.malformed if c.malformed is not None else json.dumps(c.args)
    return {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": args}}


def _tool(t: ToolSchema) -> dict[str, Any]:
    spec = {"name": t.name, "description": t.description, "parameters": t.input_schema}
    return {"type": "function", "function": spec}


def _describe(tools: Sequence[ToolSchema]) -> str:
    return "\n".join(
        f"- {t.name}: {t.description} Arguments: {json.dumps(t.input_schema)}" for t in tools
    )


make = OpenAICompatible  # the registry builds adapters through `make`
