"""One adapter for every OpenAI-compatible server [PRV-1, PRV-3, ADR-0002].

OpenAI, Azure, OpenRouter, Ollama and any `[providers.NAME]` block differ only in
the `Quirks` row they get; nothing below looks at a provider's name. The wire
format is Chat Completions, streamed:

    system        → {"role": "system", "content": "…"}
    user          → {"role": "user", "content": "…"}
    assistant     → {"role": "assistant", "content": "…", "tool_calls": [{id, function}]}
    tool results  → one {"role": "tool", "tool_call_id": …, "content": "…"} each

Chat Completions has no standard field for sending reasoning back, so reasoning
this adapter received stays in the record and is not replayed; reasoning from
another family is dropped and announced [PRV-13].
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import httpx  # loaded only once a model names an OpenAI-compatible provider [PRV-4]

from edgar.config.schema import PriceSection, ProviderSection
from edgar.core.errors import ConfigError, ProviderError
from edgar.core.events import EventBus, ReasoningDropped, TextDelta, ThinkingDelta
from edgar.core.message import ContentBlock, Message, TextBlock, ThinkingBlock
from edgar.providers.base import Capabilities, ProviderResponse, Usage
from edgar.providers.http import HttpAdapter, Retry, events, tool_calls
from edgar.providers.quirks import Quirks, quirks_for

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

    def __init__(self, name: str, quirks: Quirks, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.quirks = quirks
        self.capabilities = Capabilities(
            tools=True,
            parallel_tool_calls=quirks.parallel_tools,
            streaming=True,
            reasoning=quirks.reasoning,
            prompt_caching=False,
            max_context=quirks.max_context,
            max_output=quirks.max_output,
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

    def _url(self, model: str) -> str:
        base = (self.quirks.base_url or "").rstrip("/")
        version = self.quirks.api_version
        if version:  # Azure: the model name is the deployment name
            return f"{base}/openai/deployments/{model}/chat/completions?api-version={version}"
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        style = self.quirks.auth_style
        if style == "none" or not self.api_key:
            return {}
        return (
            {"api-key": self.api_key}
            if style == "api-key"
            else {"authorization": f"Bearer {self.api_key}"}
        )

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
                _append(out, "user", m.text)
            elif m.role == "assistant":
                dropped |= {b.origin for b in m.content if isinstance(b, ThinkingBlock)}
                # Null content is allowed only beside tool calls.
                entry: dict[str, Any] = {"role": "assistant", "content": m.text or None}
                if not m.tool_calls:
                    entry["content"] = m.text
                if m.tool_calls and native:
                    entry["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": c.malformed
                                if c.malformed is not None
                                else json.dumps(c.args),
                            },
                        }
                        for c in m.tool_calls
                    ]
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


def _tool(schema: ToolSchema) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": schema.name,
            "description": schema.description,
            "parameters": schema.input_schema,
        },
    }


def _describe(tools: Sequence[ToolSchema]) -> str:
    return "\n".join(
        f"- {t.name}: {t.description} Arguments: {json.dumps(t.input_schema)}" for t in tools
    )


def make(
    name: str,
    block: ProviderSection | None,
    *,
    env: Mapping[str, str],
    prices: Mapping[str, PriceSection],
    transport: httpx.AsyncBaseTransport | None = None,
    retry: Retry | None = None,
) -> OpenAICompatible:
    quirks = quirks_for(name, block)
    if quirks.base_url is None:
        # Azure has one host per resource, and edgar never guesses a host [PRV-15].
        url = env.get(quirks.base_url_env or "")
        if not url:
            raise ConfigError(
                f"{name}: no endpoint configured",
                hint=f"set base_url in [providers.{name}]"
                + (f", or {quirks.base_url_env}" if quirks.base_url_env else ""),
            )
        quirks = dataclasses.replace(quirks, base_url=url)
    key = None
    if quirks.api_key_env:
        key = env.get(quirks.api_key_env)
        if not key and quirks.auth_style != "none":
            raise ConfigError(
                f"{name}: the API key variable {quirks.api_key_env} is not set",
                hint=f"export {quirks.api_key_env}=… (keys live in the environment, "
                "never in config)",
            )
    return OpenAICompatible(
        name, quirks, api_key=key, prices=prices, transport=transport, retry=retry
    )
