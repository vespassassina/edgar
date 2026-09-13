"""What the two HTTP adapters share: the request with its retries, server-sent
events, error mapping, token counting and tool-call assembly.

Imported only by the adapters, which load only when a model string names them, so
httpx never loads on a run that does not reach a provider [PRV-4, NFR-1].
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import random
import re
import secrets
import time
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from edgar.config.schema import PriceSection
from edgar.context.tokens import approx_message_tokens
from edgar.core.errors import ContextOverflow, EdgarError, ProviderError
from edgar.core.events import EventBus, ProviderRetry, ToolCallRepaired
from edgar.core.message import Message, ToolUseBlock
from edgar.providers import repair
from edgar.providers.base import Usage
from edgar.providers.pricing import cost_of

RETRYABLE = frozenset({408, 409, 429, 500, 502, 503, 504, 529})  # 529: Anthropic overloaded
TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0)
_OVERFLOW = re.compile(r"context.length|context window|too long|maximum context", re.I)


@dataclass(frozen=True, slots=True)
class Retry:
    """Exponential backoff with full jitter on 429 and 5xx; Retry-After wins [PRV-7]."""

    attempts: int = 4
    base_s: float = 1.0
    cap_s: float = 60.0  # a server asking for longer than this gets an error, not a hang

    def delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        return random.uniform(0, min(self.cap_s, self.base_s * 2 ** (attempt - 1)))


class HttpAdapter:
    """State an adapter keeps between requests: one client per event loop, and
    the token-count correction learned from what the provider reports [OQ-3]."""

    name: str
    family: str

    def __init__(
        self,
        name: str,
        *,
        api_key: str | None,
        prices: Mapping[str, PriceSection],
        transport: httpx.AsyncBaseTransport | None = None,
        retry: Retry | None = None,
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.prices = prices
        self.retry = retry or Retry()
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ratio = 1.0

    def client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop:
            self._client = httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT)
            self._loop = loop
        return self._client

    def count_tokens(self, messages: Sequence[Message]) -> int:
        """Characters over four, scaled by the last observed ratio of the provider's
        own count to ours. Exact where usage is returned, close enough before
        [CTX-9, OQ-3]; the ratio also absorbs the tool schemas sent alongside."""
        return round(approx_message_tokens(messages) * self._ratio)

    def observe(self, messages: Sequence[Message], usage: Usage) -> None:
        approx = approx_message_tokens(messages)
        if usage.input_tokens and approx and not usage.approximate:
            self._ratio = usage.input_tokens / approx

    async def models(self) -> list[str]:
        """GET the provider's model list; the adapter says where (`listing`)."""
        where = self.listing()
        if where is None:
            return []
        url, headers = where
        try:
            response = await self.client().get(url, headers=headers)
        except httpx.TransportError as exc:
            raise ProviderError(f"{self.name}: cannot reach {httpx.URL(url).host}: {exc}") from exc
        if response.status_code >= 400:
            raise self.error(response)
        return sorted(str(m["id"]) for m in response.json().get("data", []) if "id" in m)

    def listing(self) -> tuple[str, dict[str, str]] | None:
        return None

    def cost(self, model: str, usage: Usage) -> float | None:
        return cost_of(f"{self.name}/{model}", usage, self.prices)

    @asynccontextmanager
    async def post(
        self, url: str, body: dict[str, Any], headers: dict[str, str], bus: EventBus
    ) -> AsyncIterator[httpx.Response]:
        """POST and hand back the streaming response, retrying before the first byte.
        Once the body starts streaming there is no retry: deltas already went out."""
        attempt = 0
        while True:
            attempt += 1
            try:
                request = self.client().build_request("POST", url, json=body, headers=headers)
                response = await self.client().send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt >= self.retry.attempts:
                    raise ProviderError(
                        f"{self.name}: cannot reach {httpx.URL(url).host}: {exc}",
                        hint="check the network, or base_url in [providers." + self.name + "]",
                    ) from exc
                await self._wait(bus, attempt, None, "connection error")
                continue
            if response.status_code < 400:
                break
            await response.aread()
            await response.aclose()
            after = _retry_after(response.headers.get("retry-after"))
            retryable = response.status_code in RETRYABLE and attempt < self.retry.attempts
            if retryable and (after is None or after <= self.retry.cap_s):
                await self._wait(bus, attempt, after, f"HTTP {response.status_code}")
                continue
            raise self.error(response)
        try:
            yield response
        finally:
            await response.aclose()

    async def _wait(self, bus: EventBus, attempt: int, after: float | None, why: str) -> None:
        delay = self.retry.delay(attempt, after)
        bus.emit(ProviderRetry(attempt=attempt, after_s=delay, reason=why))
        await asyncio.sleep(delay)

    def error(self, response: httpx.Response) -> EdgarError:
        status, message = response.status_code, error_message(response)
        where = f"{self.name}: HTTP {status}: {message}"
        if status in (401, 403):
            return ProviderError(where, hint="check the API key and that it may use this model")
        if status == 400 and _OVERFLOW.search(message):
            return ContextOverflow(where, hint="start a new session or a smaller request")
        if "tool" in message.lower() and "support" in message.lower():
            return ProviderError(
                where,
                hint=f"this model has no native tool calls; set native_tools = false "
                f"in [providers.{self.name}] to use text tool calls",
            )
        if status == 404:
            return ProviderError(where, hint="check the model name after the provider/")
        return ProviderError(where)


def error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text.strip()[:300] or response.reason_phrase
    found = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(found, dict):
        found = found.get("message", found)
    return str(found)[:300]


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:  # the other form the header may take: an HTTP date
        return max(0.0, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


async def events(response: httpx.Response) -> AsyncIterator[tuple[str, Any]]:
    """Server-sent events as (event name, decoded JSON data). `[DONE]` ends it."""
    name, data = "", []
    async for line in response.aiter_lines():
        if line.startswith(":"):
            continue
        if line:
            key, _, value = line.partition(":")
            if key == "event":
                name = value.removeprefix(" ")
            elif key == "data":
                data.append(value.removeprefix(" "))
            continue
        if data:
            if "\n".join(data).strip() == "[DONE]":
                return
            yield name or "message", _decode(data)
        name, data = "", []
    if data and "\n".join(data).strip() != "[DONE]":
        yield name or "message", _decode(data)


def _decode(data: list[str]) -> Any:
    try:
        return json.loads("\n".join(data))
    except ValueError:
        raise ProviderError(f"unreadable stream event: {' '.join(data)[:120]!r}") from None


def tool_calls(
    raw: Sequence[tuple[str | None, str, str]],
    text: str,
    tools: Collection[str],
    *,
    native: bool,
    bus: EventBus,
) -> tuple[list[ToolUseBlock], str, int]:
    """(id, name, raw arguments) → tool-use blocks, the text left over, and how
    many calls needed repair [PRV-16]."""
    calls, repairs = [], 0
    for call_id, name, arguments in raw:
        args, fixed = repair.arguments(arguments)
        if fixed is not None:
            repairs += 1
            bus.emit(ToolCallRepaired(tool=name, repair=fixed))
        malformed = None if args is not None else arguments
        calls.append(ToolUseBlock(call_id or _call_id(), name, args or {}, malformed=malformed))
    if not calls and tools:
        found = repair.text_call(text, tools, anywhere=not native)
        if found is not None:
            name, args, fixed = found
            bus.emit(ToolCallRepaired(tool=name, repair=fixed))
            return [ToolUseBlock(_call_id(), name, args)], "", 1
    return calls, text, repairs


def _call_id() -> str:
    return f"call_{secrets.token_hex(6)}"
