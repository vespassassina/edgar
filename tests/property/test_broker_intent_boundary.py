"""The intent boundary, over generated trajectories [CAP-1, MEM-8 analogue].

The invariant: whatever a session does, `Intents.current`'s text can only ever
be the text of a `PromptTyped` event at depth 0 that was actually emitted.
Nothing a tool printed, nothing the model said, nothing a subagent typed, and
no correction (`PromptSteered`) can ever end up there. This is a property test
because the interesting case is the one nobody thought of, the same reasoning
`tests/property/test_learning_boundary.py` applies to `memory.store.ACTIVE_FROM`.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from edgar.broker.intent import Intents
from edgar.core.events import Event, PromptSteered, PromptTyped, TextDelta, ToolProposed

TAINT = "qzvtaintedqzv"  # a marker no depth-0 PromptTyped step below ever carries


def _typed(text: str, depth: int) -> Event:
    return PromptTyped(text=text, depth=depth)


def _steered(text: str) -> Event:
    return PromptSteered(text=text)


def _said(text: str) -> Event:
    return TextDelta(text=text)


def _called(args: str) -> Event:
    return ToolProposed(id="c1", tool="fake", args_preview=args)


_step = st.one_of(
    st.builds(_typed, st.text(min_size=1, max_size=10), st.just(0)),
    st.builds(_typed, st.text(min_size=1, max_size=10).map(lambda s: TAINT + s), st.integers(1, 3)),
    st.builds(_steered, st.text(min_size=1, max_size=10).map(lambda s: TAINT + s)),
    st.builds(_said, st.text(min_size=1, max_size=10).map(lambda s: TAINT + s)),
    st.builds(_called, st.text(min_size=1, max_size=10).map(lambda s: TAINT + s)),
)


@given(steps=st.lists(_step, max_size=30))
def test_current_intent_text_always_traces_to_a_depth_0_typed_line(steps: list[Event]) -> None:
    intents = Intents()
    typed_at_depth_0: list[str] = []
    for step in steps:
        intents(step)
        if isinstance(step, PromptTyped) and step.depth == 0:
            typed_at_depth_0.append(step.text)
    if intents.current is None:
        assert not typed_at_depth_0
    else:
        assert intents.current.text in typed_at_depth_0
        assert TAINT not in intents.current.text
