"""Every adapter passes the same suite [ADR-0009 layer 2, PRV-1, PRV-2, PRV-12].

Four named providers share one OpenAI-compatible adapter (ADR-0002), which is
exactly where "works on OpenAI, breaks on Ollama" comes from; the parametrised
suite is what stops it. `compat` is a user-defined `[providers.local]` block
pointed at a real server on loopback, so the config-only path meets the same bar.
A new provider is done when this file passes for it.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from itertools import pairwise
from typing import Any

import cassettes
import pytest
from rig import Rig

from edgar.core.errors import ProviderError
from edgar.core.events import (
    ProviderRetry,
    ReasoningDropped,
    TextDelta,
    ThinkingDelta,
    ToolCallRepaired,
)
from edgar.core.message import (
    Message,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

PROVIDERS = ["openai", "azure", "openrouter", "ollama", "anthropic", "compat"]
FOREIGN = "elsewhere:model-x"  # reasoning from a family no adapter here belongs to

MakeRig = Callable[[str, str], Rig]


def system() -> Message:
    return Message("system", (TextBlock("You are terse. Use tools when asked."),))


def user(text: str, **meta: Any) -> Message:
    return Message.user(text, **meta)


def call_and_result(call_id: str, thinking: ThinkingBlock | None = None) -> tuple[Message, Message]:
    blocks: tuple[Any, ...] = (ToolUseBlock(call_id, "read", {"path": "a.txt"}),)
    if thinking is not None:
        blocks = (thinking, *blocks)
    result = ToolResultBlock(call_id, (TextBlock("     1\thello\n     2\tworld\n"),))
    return Message("assistant", blocks), Message("tool", (result,))


def sent(rig: Rig) -> str:
    return json.dumps(rig.body)


@pytest.mark.parametrize("name", PROVIDERS)
class TestProviderContract:
    def test_streams_text_deltas(self, rig: MakeRig, name: str) -> None:
        r = rig(name, "text")
        response = r.run([system(), user("Say hello.")], tools=[])
        deltas = r.recorder.of(TextDelta)
        assert response.message.text
        assert deltas and "".join(d.text for d in deltas) == response.message.text
        assert response.stop_reason == "end_turn"

    def test_returns_single_tool_call(self, rig: MakeRig, name: str) -> None:
        response = rig(name, "tool_call_single").run([system(), user("Read a.txt.")])
        (call,) = response.message.tool_calls
        assert (call.name, call.args, call.malformed) == ("read", {"path": "a.txt"}, None)
        assert response.stop_reason == "tool_use"

    def test_returns_parallel_tool_calls(self, rig: MakeRig, name: str) -> None:
        response = rig(name, "tool_calls_parallel").run([system(), user("Read a.txt, list src.")])
        calls = response.message.tool_calls
        assert [c.name for c in calls] == ["read", "ls"]
        assert len({c.id for c in calls}) == 2

    def test_round_trips_tool_result(self, rig: MakeRig, name: str) -> None:
        r = rig(name, "round_trip")
        response = r.run([system(), user("Read a.txt."), *call_and_result("call_rt")])
        body = sent(r)
        assert "call_rt" in body and "hello" in body  # the id and the result both travel
        assert response.message.text

    def test_preserves_own_thinking_blocks(self, rig: MakeRig, name: str) -> None:
        first = rig(name, "thinking" if rig_reasons(name) else "text")
        response = first.run([system(), user("Think, then say hi.")], tools=[])
        own = [b for b in response.message.content if isinstance(b, ThinkingBlock)]
        if rig_reasons(name):
            assert own and own[0].family == first.provider.family
            assert first.recorder.of(ThinkingDelta)
        else:
            assert own == []  # it said it would not stream reasoning, and it did not

        # Sending our own reasoning back is never a "drop".
        again = rig(name, "replay")
        thought = own[0] if own else ThinkingBlock("x", f"{again.provider.family}:m", "sig")
        again.run([system(), user("Read a.txt."), *call_and_result("call_own", thought)])
        assert again.recorder.of(ReasoningDropped) == []

    def test_drops_foreign_thinking_blocks(self, rig: MakeRig, name: str) -> None:  # [PRV-13]
        r = rig(name, "replay")
        foreign = ThinkingBlock("SECRET-REASONING", FOREIGN, "their-signature")
        r.run([system(), user("Read a.txt."), *call_and_result("call_f", foreign)])
        (dropped,) = r.recorder.of(ReasoningDropped)
        assert (dropped.from_origin, dropped.to_family) == (FOREIGN, r.provider.family)
        assert "SECRET-REASONING" not in sent(r) and "their-signature" not in sent(r)

    def test_repairs_fenced_tool_call(self, rig: MakeRig, name: str) -> None:  # [PRV-16]
        r = rig(name, "fenced")
        response = r.run([system(), user("Read a.txt.")])
        (call,) = response.message.tool_calls
        assert (call.name, call.args) == ("read", {"path": "a.txt"})
        assert response.message.text == ""
        assert [e.repair for e in r.recorder.of(ToolCallRepaired)] == ["fence"]
        assert response.usage.repairs == 1

    def test_accepts_tool_turn_after_family_switch(self, rig: MakeRig, name: str) -> None:
        # Fallback moved the turn here from another family: reasoning is off until
        # the next user turn, and the transcript must still be accepted [PRV-13].
        r = rig(name, "replay")
        foreign = ThinkingBlock("theirs", FOREIGN, "sig")
        transcript = [system(), user("Read a.txt."), *call_and_result("call_sw", foreign)]
        response = r.run(transcript, reasoning=False)
        assert response.message.text
        assert "thinking" not in r.body  # no reasoning requested
        assert "call_sw" in sent(r)

    def test_merges_a_steer_after_tool_results(self, rig: MakeRig, name: str) -> None:
        # /steer lands after a complete unit; the request must still be valid, and
        # roles that must alternate are merged, results first [CLI-13, ADR-0028].
        r = rig(name, "replay")
        transcript = [
            system(),
            user("Read a.txt."),
            *call_and_result("call_st"),
            user("also list src", via="steer"),
        ]
        r.run(transcript)
        roles = [m["role"] for m in r.body["messages"]]
        assert all(a != b or a == "tool" for a, b in pairwise(roles))
        body = sent(r)
        assert body.index("call_st") < body.index("also list src")

    def test_reports_usage(self, rig: MakeRig, name: str) -> None:
        response = rig(name, "text").run([system(), user("Say hello.")], tools=[])
        usage = response.usage
        assert usage.input_tokens > 0 and usage.output_tokens > 0
        assert not usage.approximate
        assert response.cost is None or response.cost >= 0  # None is "unknown", never 0

    def test_maps_auth_error_to_provider_error(self, rig: MakeRig, name: str) -> None:
        with pytest.raises(ProviderError) as info:
            rig(name, "auth_error").run([system(), user("hi")])
        assert "401" in str(info.value) and "API key" in (info.value.hint or "")
        assert info.value.exit_code == 4

    def test_retries_429_then_succeeds(self, rig: MakeRig, name: str) -> None:  # [PRV-7]
        r = rig(name, "retry_429")
        response = r.run([system(), user("Say hello.")], tools=[])
        assert response.message.text
        (retry,) = r.recorder.of(ProviderRetry)
        assert (retry.attempt, retry.after_s, retry.reason) == (1, 0.0, "HTTP 429")
        assert len(r.requests) == 2

    def test_cancellation_stops_stream_promptly(self, rig: MakeRig, name: str) -> None:
        r = rig(name, "cancel")

        async def scenario() -> float:
            first = asyncio.Event()
            r.bus.subscribe(lambda e: first.set() if isinstance(e, TextDelta) else None)
            task = asyncio.create_task(r.call([system(), user("Count slowly.")], tools=[]))
            await asyncio.wait_for(first.wait(), 5)
            started = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return time.monotonic() - started

        assert asyncio.run(scenario()) < 0.5
        assert len(r.recorder.of(TextDelta)) < 10  # it stopped; it did not drain the stream

    def test_declares_capabilities_truthfully(self, rig: MakeRig, name: str) -> None:
        r = rig(name, "text")
        caps = r.provider.capabilities
        assert caps.tools and caps.streaming
        assert caps.max_context >= 4_096 and 256 <= caps.max_output <= caps.max_context
        assert caps.reasoning == rig_reasons(name)
        assert r.provider.family in ("openai-compatible", "anthropic")

    def test_normalises_to_canonical_messages(self, rig: MakeRig, name: str) -> None:
        for scenario in ("text", "tool_calls_parallel"):
            response = rig(name, scenario).run([system(), user("Go.")])
            message = response.message
            assert message.role == "assistant"
            for block in message.content:
                assert isinstance(block, TextBlock | ThinkingBlock | ToolUseBlock)
                if isinstance(block, ToolUseBlock):
                    assert block.id and isinstance(block.args, dict)


def rig_reasons(name: str) -> bool:
    return "thinking" in cassettes.load(name)


def test_no_cassette_holds_a_secret() -> None:
    for path in sorted(cassettes.CASSETTES.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for pattern in cassettes.SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"


def test_every_provider_has_every_scenario() -> None:
    expected = set(cassettes.synthetic("openai"))
    for name in PROVIDERS:
        assert expected <= set(cassettes.load(name)), name
