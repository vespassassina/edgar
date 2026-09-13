"""Compaction's pure stages [CTX-4, CTX-5, CTX-8, CTX-11, CTX-14].

Every stage works on a view and a cut point on a turn boundary, so it must keep the
pairing invariant, leave the first prompt and the turn in progress alone, do
nothing the second time, and replay exactly from its record.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from edgar.context.compact import ELIDED, apply, elide, fold, rewind, turn_starts
from edgar.core.message import Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock
from edgar.core.units import pairing_violations

Turn = list[int]  # the number of tool calls in each exchange of the turn


def conversation(turns: list[Turn]) -> list[Message]:
    out: list[Message] = []
    n = 0
    for t, exchanges in enumerate(turns):
        out.append(Message.user(f"prompt {t}"))
        for calls in exchanges:
            ids = [f"tu_{n + i}" for i in range(calls)]
            n += calls
            uses = tuple(ToolUseBlock(i, "write", {"path": f"f{i}.txt"}) for i in ids)
            out.append(Message("assistant", (ThinkingBlock("hmm", "fake:test"), *uses)))
            text = (TextBlock("x" * 400),)
            out.append(Message("tool", tuple(ToolResultBlock(i, text) for i in ids)))
        out.append(Message("assistant", (ThinkingBlock("so", "fake:test"), TextBlock("done"))))
    return out


views = st.builds(conversation, st.lists(st.lists(st.integers(1, 3), max_size=3), max_size=8))


@st.composite
def view_and_cut(draw: st.DrawFn) -> tuple[list[Message], int]:
    view = draw(views)
    starts = turn_starts(view)
    return view, draw(st.sampled_from(starts)) if starts else 0


@given(view_and_cut())
def test_elide_keeps_the_pairing_and_is_idempotent(case: tuple[list[Message], int]) -> None:
    view, cut = case
    once = elide(view, cut)
    assert pairing_violations(once) == []
    assert elide(once, cut) == once  # [CTX-8]
    assert once[cut:] == view[cut:]
    assert [m.role for m in once] == [m.role for m in view]  # stubs, never removals
    assert all(r.text.startswith(ELIDED) for m in once[:cut] for r in m.tool_results)


@given(views)
def test_elide_never_touches_thinking_in_the_turn_in_progress(view: list[Message]) -> None:
    """Providers need the current turn's thinking unchanged, even under S3 [CTX-4]."""
    if not view:
        return
    last = turn_starts(view)[-1]
    elided = elide(view, len(view) - 1)
    for before, after in zip(view[last:], elided[last:], strict=True):
        assert [b for b in before.content if isinstance(b, ThinkingBlock)] == [
            b for b in after.content if isinstance(b, ThinkingBlock)
        ]


@given(view_and_cut())
def test_fold_leaves_one_summary_and_the_first_prompt(case: tuple[list[Message], int]) -> None:
    view, cut = case
    if cut <= 1:
        return
    folded = fold(fold(view, cut, "first"), 2, "second")
    assert folded[0] == view[0]  # never compacted [CTX-5]
    assert [m.text for m in folded if m.meta.get("via") == "summary"] == ["second"]
    assert pairing_violations(folded) == []


@given(views, st.integers(1, 10))
def test_rewind_removes_whole_turns_and_names_the_files(view: list[Message], n: int) -> None:
    kept, files = rewind(view, n)
    assert pairing_violations(kept) == []
    assert len(turn_starts(kept)) == max(len(turn_starts(view)) - n, 0)
    assert view[: len(kept)] == kept
    gone = view[len(kept) :]
    assert files == sorted({str(c.args["path"]) for m in gone for c in m.tool_calls})


@given(view_and_cut())
def test_records_replay_to_the_same_view(case: tuple[list[Message], int]) -> None:
    """What `--resume` does with a compaction record [CTX-14]."""
    view, cut = case
    live = fold(elide(view, cut), cut, "summary") if cut > 1 else elide(view, cut)
    records = [{"type": "compaction", "stage": "S1", "upto": cut, "summary": None}]
    if cut > 1:
        records.append({"type": "compaction", "stage": "S2", "upto": cut, "summary": "summary"})
    replayed = view
    for entry in records:
        replayed = apply(replayed, entry)
    assert replayed == live
