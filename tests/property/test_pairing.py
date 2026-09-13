"""The pairing invariant [CTX-4]: the most important property in the repo.

Generated transcripts that respect it must pass, and every way of breaking it that
compaction, cancellation or a misplaced steer could produce must be caught.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from edgar.core.message import Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock
from edgar.core.units import complete_prefix, pairing_violations, units

UnitSpec = tuple[str, int, list[int]]  # kind, number of calls, result order


@st.composite
def unit_specs(draw: st.DrawFn) -> UnitSpec:
    kind = draw(st.sampled_from(["user", "assistant", "exchange"]))
    calls = draw(st.integers(1, 3)) if kind == "exchange" else 0
    order = draw(st.permutations(list(range(calls))))
    return kind, calls, list(order)


def build(specs: list[UnitSpec], *, thinking: bool = False) -> list[Message]:
    out: list[Message] = []
    next_id = 0
    for kind, n, order in specs:
        if kind == "user":
            out.append(Message.user("do something"))
        elif kind == "assistant":
            out.append(Message("assistant", (TextBlock("done"),)))
        else:
            ids = [f"tu_{next_id + i}" for i in range(n)]
            next_id += n
            head = (ThinkingBlock("hmm", "fake:test"),) if thinking else ()
            calls = tuple(ToolUseBlock(i, "read", {"path": "a.txt"}) for i in ids)
            out.append(Message("assistant", (*head, *calls)))
            results = tuple(ToolResultBlock(ids[j], (TextBlock("ok"),)) for j in order)
            out.append(Message("tool", results))
    return out


transcripts = st.builds(build, st.lists(unit_specs(), max_size=12), thinking=st.booleans())


@given(transcripts)
def test_well_formed_transcripts_satisfy_the_invariant(transcript: list[Message]) -> None:
    assert pairing_violations(transcript) == []


@given(transcripts)
def test_units_partition_the_transcript(transcript: list[Message]) -> None:
    parts = units(transcript)
    assert [m for u in parts for m in u.messages] == transcript
    for unit in parts:
        if unit.is_tool_exchange:
            call, result = unit.messages
            assert call.tool_calls and result.role == "tool"
        else:
            assert not unit.messages[0].tool_calls


def _exchanges(transcript: list[Message]) -> list[int]:
    return [i for i, m in enumerate(transcript) if m.tool_calls]


@given(transcripts, st.data())
def test_dropping_a_tool_message_is_caught(transcript: list[Message], data: st.DataObject) -> None:
    starts = _exchanges(transcript)
    if not starts:
        return
    i = data.draw(st.sampled_from(starts))
    assert pairing_violations(transcript[: i + 1] + transcript[i + 2 :])


@given(transcripts, st.data())
def test_a_message_between_call_and_result_is_caught(
    transcript: list[Message], data: st.DataObject
) -> None:
    starts = _exchanges(transcript)
    if not starts:
        return
    i = data.draw(st.sampled_from(starts))
    intruder = data.draw(st.sampled_from([Message.user("steer"), Message("assistant", ())]))
    assert pairing_violations([*transcript[: i + 1], intruder, *transcript[i + 1 :]])


@given(transcripts, st.data())
def test_a_missing_or_foreign_result_is_caught(
    transcript: list[Message], data: st.DataObject
) -> None:
    starts = _exchanges(transcript)
    if not starts:
        return
    i = data.draw(st.sampled_from(starts)) + 1
    results = transcript[i].tool_results
    damaged = data.draw(
        st.sampled_from(
            [
                results[1:],  # one result missing
                (*results, results[0]),  # one result twice
                (*results[1:], ToolResultBlock("tu_foreign", (TextBlock("?"),))),
            ]
        )
    )
    broken = [*transcript[:i], Message("tool", damaged), *transcript[i + 1 :]]
    assert pairing_violations(broken)


def test_results_outside_a_tool_message_and_calls_outside_an_assistant_are_caught() -> None:
    call = ToolUseBlock("tu_1", "read", {})
    result = ToolResultBlock("tu_1", (TextBlock("ok"),))
    assert pairing_violations([Message("user", (call,)), Message("tool", (result,))])
    assert pairing_violations([Message("user", (result,))])
    assert pairing_violations([Message("assistant", (call, call)), Message("tool", (result,))])


@given(transcripts)
def test_complete_prefix_drops_an_open_unit(transcript: list[Message]) -> None:
    open_call = Message("assistant", (ToolUseBlock("tu_open", "read", {"path": "x"}),))
    assert pairing_violations(complete_prefix([*transcript, open_call])) == []
    assert complete_prefix(transcript) == transcript
