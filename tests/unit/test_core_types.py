"""Messages, sessions, events and the fake provider's own behaviour."""

from __future__ import annotations

import asyncio
import dataclasses
import re
from pathlib import Path

import pytest
from harness import Recorder
from scripted import ScriptedProvider, ScriptedResponse

from edgar.core.errors import ConfigError, ProviderError
from edgar.core.events import EventBus, TextDelta
from edgar.core.message import Message, TextBlock, ThinkingBlock
from edgar.core.session import Session, new_id
from edgar.providers.base import Usage
from edgar.providers.registry import resolve


def test_messages_are_immutable() -> None:
    message = Message.user("hi")
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.role = "assistant"  # type: ignore[misc]  # the point of the test


def test_ids_are_ulids_and_sort_by_creation() -> None:
    first, second = new_id(), new_id()
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", first)
    assert first[:10] <= second[:10]


def test_steers_are_delivered_once_as_user_messages(tmp_path: Path) -> None:
    session = Session(cwd=tmp_path, model="fake/test", mode="ask")
    session.steer("one")
    session.steer("two")
    assert session.steers_pending()
    assert session.drain_steers() == ["one", "two"]
    assert not session.steers_pending() and session.drain_steers() == []
    assert [m.text for m in session.transcript] == ["one", "two"]


def test_bus_delivers_in_subscription_order() -> None:
    bus, seen = EventBus(), []
    bus.subscribe(lambda e: seen.append(("a", e.name)))
    bus.subscribe(lambda e: seen.append(("b", e.name)))
    bus.emit(TextDelta(text="x"))
    assert seen == [("a", "TextDelta"), ("b", "TextDelta")]


def _stream(provider: ScriptedProvider, messages: list[Message], recorder: Recorder) -> Message:
    bus = EventBus()
    bus.subscribe(recorder)
    return asyncio.run(provider.stream(messages, [], model="test", bus=bus)).message


def test_fake_streams_chunks_and_thinking(recorder: Recorder) -> None:
    provider = ScriptedProvider([ScriptedResponse(text="abcdef", thinking="plan", stream_chunks=3)])
    message = _stream(provider, [Message.user("hi")], recorder)
    assert recorder.names == ["ThinkingDelta", "TextDelta", "TextDelta", "TextDelta"]
    assert message.text == "abcdef"
    thinking = message.content[0]
    assert isinstance(thinking, ThinkingBlock) and thinking.origin == "fake:test"


def test_fake_script_exhaustion_and_unknown_models(recorder: Recorder) -> None:
    with pytest.raises(ProviderError, match="exhausted"):
        _stream(ScriptedProvider([]), [Message.user("hi")], recorder)
    with pytest.raises(ProviderError, match="no model 'other'"):
        asyncio.run(
            ScriptedProvider().stream([Message.user("hi")], [], model="other", bus=EventBus())
        )


def test_fake_rules(recorder: Recorder) -> None:
    provider = ScriptedProvider()
    assert _stream(provider, [Message.user("ls src")], recorder).tool_calls[0].args == {
        "path": "src"
    }
    assert _stream(provider, [Message.user("read")], recorder).text == "fake/test heard: read"


def test_usage_adds() -> None:
    assert Usage(1, 2, 3, 4) + Usage(1, 1, 1, 1) == Usage(2, 3, 4, 5)


@pytest.mark.parametrize("model", ["fake", "fake/", "/test", "nothing"])
def test_model_strings_must_name_provider_and_model(model: str) -> None:
    with pytest.raises(ConfigError, match="provider/model"):
        resolve(model)


def test_text_block_defaults_to_typed_text() -> None:
    assert TextBlock("x").attached is False
