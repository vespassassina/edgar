"""Cassettes: HTTP exchanges replayed offline [ADR-0009 layer 3].

One file per provider in tests/cassettes/, one entry per contract scenario. Each
entry says where it came from: `synthetic` entries are written by
`python tests/support/cassettes.py synthesize` from the wire formats in wire.py;
`recorded` ones come from `just record-cassettes`, which runs the contract suite
against the live API and replaces the synthetic entry. Error scenarios stay
synthetic: nobody records a 401 on purpose.

Secrets are scrubbed when recorded, not when committed, and a test checks that no
cassette holds anything shaped like a key.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import re
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from wire import Reply, anthropic_sse, error, ok, openai_sse

CASSETTES = Path(__file__).resolve().parents[1] / "cassettes"
PROVIDERS = ("openai", "azure", "openrouter", "ollama", "anthropic", "compat")
REASONING = {"openrouter", "ollama", "compat", "anthropic"}  # servers that stream reasoning
# Errors nobody triggers on purpose, and a fenced call no capable model sends.
UNRECORDABLE = {"auth_error", "retry_429", "cancel", "fenced"}
COUNTING = "one two three four five six seven eight nine ten"

SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"sk-[A-Za-z0-9_-]{16,}",
        r"sk-ant-[A-Za-z0-9_-]{16,}",
        r"sk-or-[A-Za-z0-9_-]{16,}",
        r"org-[A-Za-z0-9]{16,}",
        r"Bearer\s+[A-Za-z0-9._-]{16,}",
        r"[a-f0-9]{32}",  # Azure keys
    )
]


def scrub(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("REDACTED", text)
    return text


@dataclass
class Captured:
    url: str
    headers: dict[str, str]
    body: Any


class _Body(httpx.AsyncByteStream):
    def __init__(self, body: str, delay_s: float) -> None:
        self.parts = [p for p in re.split(r"(?<=\n\n)", body) if p]
        self.delay_s = delay_s

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for part in self.parts:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            yield part.encode()


class Replay(httpx.AsyncBaseTransport):
    """Serves exchanges in order and keeps every request for assertions."""

    def __init__(self, exchanges: list[dict[str, Any]]) -> None:
        self.queue = list(exchanges)
        self.requests: list[Captured] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append(Captured(str(request.url), dict(request.headers), body))
        exchange = self.queue.pop(0)
        stream = _Body(exchange["body"], exchange.get("delay_s", 0.0))
        return httpx.Response(exchange["status"], headers=exchange["headers"], stream=stream)


class Recording(httpx.AsyncBaseTransport):
    """Forwards to the real API and keeps each exchange, scrubbed."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.exchanges: list[dict[str, Any]] = []
        self.requests: list[Captured] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(Captured(str(request.url), {}, json.loads(request.content or b"null")))
        response = await self.inner.handle_async_request(request)
        body = b"".join([part async for part in response.stream])  # type: ignore[union-attr]
        kept = {k: v for k, v in response.headers.items() if k in ("content-type", "retry-after")}
        exchange = {"status": response.status_code, "headers": kept, "body": scrub(body.decode())}
        self.exchanges.append(exchange)
        return httpx.Response(response.status_code, headers=kept, content=body)


def load(provider: str) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(
        (CASSETTES / f"{provider}.json").read_text(encoding="utf-8")
    )
    return data


def save(provider: str, scenarios: dict[str, dict[str, Any]]) -> None:
    CASSETTES.mkdir(exist_ok=True)
    text = json.dumps(dict(sorted(scenarios.items())), indent=2, ensure_ascii=False) + "\n"
    (CASSETTES / f"{provider}.json").write_text(text, encoding="utf-8", newline="\n")


_RECORDED: set[tuple[str, str]] = set()


def record(provider: str, scenario: str, exchanges: list[dict[str, Any]]) -> None:
    """The first test to use a scenario records it; later ones in the same run only
    replay-check against the live API. Otherwise the last writer wins, and a test
    that reuses a scenario with a looser prompt overwrites the one that owns it."""
    if (provider, scenario) in _RECORDED:
        return
    _RECORDED.add((provider, scenario))
    scenarios = load(provider)
    today = datetime.date.today().isoformat()
    scenarios[scenario] = {"source": f"recorded {today}", "exchanges": exchanges}
    save(provider, scenarios)


def synthetic(provider: str) -> dict[str, dict[str, Any]]:
    anthropic = provider == "anthropic"

    def reply(r: Reply) -> str:
        return anthropic_sse(r) if anthropic else openai_sse(r, provider)  # type: ignore[arg-type]

    prefix = "toolu_0" if anthropic else "call_"
    read = (f"{prefix}1", "read", {"path": "a.txt"})
    ls = (f"{prefix}2", "ls", {"path": "src"})
    cost = 0.000042 if provider == "openrouter" else None
    if anthropic:
        denied = {
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        }
        limited = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    else:
        denied = {"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}}
        limited = {"error": {"message": "Rate limit reached", "code": "rate_limit_exceeded"}}
    fence = '```json\n{"name": "read", "arguments": {"path": "a.txt"}}\n```'
    scenarios: dict[str, list[dict[str, Any]]] = {
        "text": [ok(reply(Reply(text="Hello there.", cost=cost)))],
        "tool_call_single": [ok(reply(Reply(calls=[read])))],
        "tool_calls_parallel": [ok(reply(Reply(calls=[read, ls])))],
        "round_trip": [ok(reply(Reply(text="The file says hello, then world.")))],
        "replay": [ok(reply(Reply(text="Done.")))],
        "fenced": [ok(reply(Reply(text=fence)))],
        "auth_error": [error(401, denied)],
        "retry_429": [error(429, limited, retry_after="0"), ok(reply(Reply(text="Hello there.")))],
        "cancel": [ok(reply(Reply(text=COUNTING, pieces=10))) | {"delay_s": 0.1}],
    }
    if provider in REASONING:
        scenarios["thinking"] = [ok(reply(Reply(reasoning="They want a greeting.", text="Hi.")))]
    return {name: {"source": "synthetic", "exchanges": ex} for name, ex in scenarios.items()}


def synthesize() -> None:
    """Write synthetic entries, keeping every recorded one."""
    for provider in PROVIDERS:
        path = CASSETTES / f"{provider}.json"
        existing = load(provider) if path.exists() else {}
        kept = {k: v for k, v in existing.items() if v["source"].startswith("recorded")}
        save(provider, synthetic(provider) | kept)


if __name__ == "__main__":
    if sys.argv[1:] != ["synthesize"]:
        sys.exit("usage: python tests/support/cassettes.py synthesize")
    synthesize()
