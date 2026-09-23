"""A delegation chain can only widen, never drop a caveat [CAP-5, ADR-0039].

`verify_chain()` is the one thing standing between "the child inherited
everything the parent had" and a leaked ticket spending less than it was
scoped to. This file generates honest chains (built only through `attenuate()`)
and hostile ones (a child hand-built with one of the parent's caveats missing),
and asserts the first always verifies and the second never does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from edgar.broker.caveats import Caveat
from edgar.broker.ticket import Ticket, attenuate, verify_chain

_NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)

# Real caveats only ever reach a Ticket through parse_scope(), which validates
# calls= and until= into an int string and an ISO instant respectively -- so
# the generator matches that shape instead of exercising values no caller
# could actually produce.
_values_by_kind = {
    "tools": st.sampled_from(["a", "b", "c"]),
    "paths": st.sampled_from(["a", "b", "c"]),
    "hosts": st.sampled_from(["a", "b", "c"]),
    "calls": st.integers(min_value=1, max_value=100).map(str),
    "until": st.integers(min_value=1, max_value=10_000).map(
        lambda n: (_NOW + timedelta(seconds=n)).isoformat()
    ),
}

caveat_sets = st.lists(
    st.sampled_from(list(_values_by_kind)).flatmap(
        lambda kind: st.builds(Caveat, kind=st.just(kind), value=_values_by_kind[kind])
    ),
    max_size=4,
    unique_by=lambda c: c.kind,
).map(tuple)


@given(root=caveat_sets, extra=caveat_sets, subject=st.text(min_size=1, max_size=10))
def test_honest_attenuation_always_verifies(
    root: tuple[Caveat, ...], extra: tuple[Caveat, ...], subject: str
) -> None:
    parent = Ticket(intent_id="i1", caveats=root)
    child = attenuate(parent, subject=subject, extra=extra)
    assert verify_chain(child) is True


@given(root=caveat_sets, dropped=st.integers(min_value=0, max_value=3))
def test_a_child_missing_one_parent_caveat_never_verifies(
    root: tuple[Caveat, ...], dropped: int
) -> None:
    if not root:
        return
    index = dropped % len(root)
    forged = Ticket(
        intent_id="i1", caveats=root[:index] + root[index + 1 :], parent=Ticket("i1", caveats=root)
    )
    assert verify_chain(forged) is False
