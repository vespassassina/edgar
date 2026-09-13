"""Tool-call repair is syntactic, deterministic and never guesses [PRV-16]."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from edgar.providers.repair import arguments, text_call

TOOLS = {"read", "ls"}


@pytest.mark.parametrize(
    ("raw", "expected", "repair"),
    [
        ('{"path": "a.txt"}', {"path": "a.txt"}, None),
        ("", {}, None),
        ('```json\n{"path": "a.txt"}\n```', {"path": "a.txt"}, "fence"),
        ('```\n{"path": "a.txt"}\n```', {"path": "a.txt"}, "fence"),
        ('{"path": "a.txt"} and then I will read it', {"path": "a.txt"}, "trailing-text"),
        ('```json\n{"path": "a.txt"}\nok\n```', {"path": "a.txt"}, "trailing-text"),
    ],
)
def test_arguments_repairs(raw: str, expected: dict[str, str], repair: str | None) -> None:
    assert arguments(raw) == (expected, repair)


@pytest.mark.parametrize("raw", ['{"path": ', "path=a.txt", '["a.txt"]', "null", "I read it"])
def test_what_cannot_be_repaired_is_left_for_the_model(raw: str) -> None:
    assert arguments(raw) == (None, None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"name": "read", "arguments": {"path": "a"}}', ("read", {"path": "a"}, "text-call")),
        ('```json\n{"name": "ls", "parameters": {}}\n```', ("ls", {}, "fence")),
        (
            '{"name": "read", "input": "{\\"path\\": \\"a\\"}"}',
            ("read", {"path": "a"}, "text-call"),
        ),
        (
            '{"name": "read", "arguments": {"path": "a"}}\nDone.',
            ("read", {"path": "a"}, "text-call"),
        ),
    ],
)
def test_a_reply_that_is_a_call_becomes_one(text: str, expected: tuple[object, ...]) -> None:
    assert text_call(text, TOOLS, anywhere=False) == expected


@pytest.mark.parametrize(
    "text",
    [
        'Here is the JSON you asked for: {"name": "read", "arguments": {}}',
        '{"name": "reed", "arguments": {"path": "a"}}',  # no fuzzy names
        '{"name": "read", "arguments": ["a"]}',
        '{"tool": "read"}',
        "Just an answer.",
    ],
)
def test_explaining_json_is_not_calling_a_tool(text: str) -> None:
    assert text_call(text, TOOLS, anywhere=False) is None


def test_servers_without_native_tools_may_call_from_inside_text() -> None:
    text = 'I will look.\n```json\n{"name": "read", "arguments": {"path": "a"}}\n```'
    assert text_call(text, TOOLS, anywhere=False) is None
    assert text_call(text, TOOLS, anywhere=True) == ("read", {"path": "a"}, "fence")


@given(st.dictionaries(st.text(max_size=8), st.integers() | st.text(max_size=8), max_size=4))
def test_valid_arguments_are_never_changed(args: dict[str, object]) -> None:
    assert arguments(json.dumps(args)) == (args, None)


_names = st.sampled_from(sorted(TOOLS))
_args = st.dictionaries(st.text("abcxyz_", min_size=1, max_size=6), st.text(max_size=6), max_size=3)
_damage: dict[str, Callable[[str], str]] = {
    "fence": lambda s: f"```json\n{s}\n```",
    "text-call": lambda s: s,
    "trailing-text": lambda s: f"{s}\nThat should do it.",
}


@given(name=_names, args=_args, damage=st.sampled_from(sorted(_damage)))
def test_repair_recovers_syntactic_damage(name: str, args: dict[str, str], damage: str) -> None:
    rendered = json.dumps({"name": name, "arguments": args})
    found = text_call(_damage[damage](rendered), TOOLS, anywhere=False)
    assert found is not None and found[:2] == (name, args)


@given(text=st.text(max_size=200), anywhere=st.booleans())
def test_repair_never_invents_a_call(text: str, anywhere: bool) -> None:
    found = text_call(text, TOOLS, anywhere=anywhere)
    assert found is None or found[0] in text  # only a name that was there
