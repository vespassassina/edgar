"""Intent creation: typed lines only, depth 0 only [CAP-1]."""

from __future__ import annotations

from edgar.broker.intent import Intents
from edgar.core.events import PromptSteered, PromptTyped, TextDelta


def test_starts_with_no_intent() -> None:
    assert Intents().current is None


def test_a_typed_line_at_depth_0_opens_an_intent() -> None:
    intents = Intents()
    intents(PromptTyped(text="do the thing"))
    assert intents.current is not None
    assert intents.current.text == "do the thing"


def test_a_typed_line_replaces_the_current_intent() -> None:
    intents = Intents()
    intents(PromptTyped(text="first"))
    first_id = intents.current.id if intents.current else None
    intents(PromptTyped(text="second"))
    assert intents.current is not None
    assert intents.current.text == "second"
    assert intents.current.id != first_id


def test_a_typed_line_at_a_deeper_depth_is_ignored() -> None:
    intents = Intents()
    intents(PromptTyped(text="subagent line", depth=1))
    assert intents.current is None


def test_a_steer_does_not_open_a_new_intent() -> None:
    intents = Intents()
    intents(PromptTyped(text="original"))
    intents(PromptSteered(text="correction"))
    assert intents.current is not None
    assert intents.current.text == "original"


def test_other_event_kinds_are_ignored() -> None:
    intents = Intents()
    intents(TextDelta(text="the model said something"))
    assert intents.current is None
