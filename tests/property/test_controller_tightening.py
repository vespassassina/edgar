"""A machine may tighten policy and may never loosen it [CTRL-8, PERM-8, ADR-0021].

`narrow()` is a pure function over two values, which is exactly the shape a
generated test is good at: the dangerous case is not the loosening somebody thought
to write down, it is the combination of four fields nobody pictured. So this file
generates policies and narrowings together, including deliberately hostile ones, and
asserts one thing on every pair — whatever comes back is at least as strict as what
went in, or it is a refusal.

The second assertion is worth as much as the first: `narrow()` must not silently
drop a field it did not like. A refusal is a string naming the field, and a success
has to have applied every part of the narrowing it accepted.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from edgar.controller.tighten import MODES, VERDICTS, Narrowing, is_narrowing, narrow
from edgar.permissions.policy import Policy

PATTERNS = ["./**", "./src/**", "./docs/**", "./tests/**"]
TOOLS = ["shell", "write", "edit", "read", "fetch"]

policies = st.builds(
    Policy,
    mode=st.sampled_from(MODES),
    cwd=st.just(Path("/w")),
    home=st.just(Path("/h")),
    rules=st.dictionaries(st.sampled_from(TOOLS), st.sampled_from(VERDICTS), max_size=5),
    write_paths=st.lists(st.sampled_from(PATTERNS), max_size=4, unique=True).map(tuple),
    shell_deny=st.lists(st.sampled_from(["rm -rf", "curl", "sudo"]), max_size=3, unique=True).map(
        tuple
    ),
)

# Deliberately unconstrained: a narrowing is whatever a model returned, so the
# generator is allowed to name a looser mode, an unknown verdict, a pattern the
# policy never had, and the word "allow" that is always refused.
narrowings = st.builds(
    Narrowing,
    mode=st.one_of(st.none(), st.sampled_from([*MODES, "god-mode", ""])),
    shell_deny=st.lists(st.sampled_from(["rm -rf", "curl", "wget"]), max_size=3).map(tuple),
    write_paths=st.one_of(
        st.none(), st.lists(st.sampled_from([*PATTERNS, "/etc/**"]), max_size=4).map(tuple)
    ),
    rules=st.dictionaries(
        st.sampled_from(TOOLS), st.sampled_from([*VERDICTS, "maybe"]), max_size=5
    ),
)


@given(policy=policies, want=narrowings)
def test_the_answer_is_always_a_narrowing_or_a_refusal(policy: Policy, want: Narrowing) -> None:
    result = narrow(policy, want)
    if isinstance(result, str):
        assert result  # a refusal says which field, never an empty string
        return
    assert is_narrowing(result, policy)


@given(policy=policies, want=narrowings)
def test_a_narrowing_never_touches_a_field_outside_the_four(
    policy: Policy, want: Narrowing
) -> None:
    # Grants, taint and the interactive flag are the human's; the controller
    # cannot reach them even by accident.
    result = narrow(policy, want)
    if isinstance(result, str):
        return
    assert result.grants == policy.grants
    assert result.tainted == policy.tainted
    assert result.interactive == policy.interactive
    assert result.shell_allow == policy.shell_allow
    assert result.cwd == policy.cwd and result.home == policy.home


@given(policy=policies, want=narrowings)
def test_applying_the_same_narrowing_twice_changes_nothing_more(
    policy: Policy, want: Narrowing
) -> None:
    # A controller that trips on the same signal every turn must not ratchet.
    once = narrow(policy, want)
    if isinstance(once, str):
        return
    twice = narrow(once, want)
    assert not isinstance(twice, str)
    assert twice == once


@given(policy=policies)
def test_an_explicit_allow_is_refused_however_strict_the_policy_already_is(
    policy: Policy,
) -> None:
    # An explicit allow overrides the mode's own default, so it widens even when
    # it looks like a no-op next to a read-only policy.
    assert isinstance(narrow(policy, Narrowing(rules={"shell": "allow"})), str)


@given(policy=policies)
def test_the_loosest_mode_is_never_reachable_from_a_stricter_one(policy: Policy) -> None:
    result = narrow(policy, Narrowing(mode="yolo"))
    if policy.mode == "yolo":
        assert not isinstance(result, str)
    else:
        assert isinstance(result, str) and "looser" in result


@given(policy=policies, want=narrowings)
def test_an_accepted_narrowing_was_actually_applied(policy: Policy, want: Narrowing) -> None:
    # The failure this catches is a narrow() that keeps the policy unchanged and
    # calls it a success: still a narrowing, but not the one that was asked for.
    result = narrow(policy, want)
    if isinstance(result, str):
        return
    if want.mode is not None:
        assert result.mode == want.mode
    assert set(want.shell_deny) <= set(result.shell_deny)
    if want.write_paths is not None:
        assert result.write_paths == tuple(want.write_paths)
    for tool, verdict in want.rules.items():
        assert result.rules[tool] == verdict
