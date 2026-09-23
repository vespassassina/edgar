"""Every action the controller may ask for, and everything it may not [CTRL-4, CTRL-5].

The proposals here are fabricated: no model is called, and none will be in M13's
tests. The point is the parser, which is the whole whitelist — a string that is not
one of the eight never reaches a builder, so this file is where the boundary is
actually checked.
"""

from __future__ import annotations

import pytest

from edgar.config.schema import ModelSection
from edgar.controller.proposals import (
    ACTIONS,
    Abort,
    Compact,
    Noop,
    ProposeInstruction,
    ProposeSkill,
    Rejected,
    SwitchModel,
    TightenPolicy,
    WarnUser,
    parse,
    targets,
)
from edgar.providers.routing import Route

MODELS = frozenset({"gpt-5-mini", "claude-sonnet-4"})


def fabricate(**fields: object) -> str:
    import json

    return json.dumps(fields)


# Each of the eight, once, with a proposal a model could plausibly return.
EIGHT: tuple[tuple[str, dict[str, object], type], ...] = (
    ("compact", {"compact_at": 0.5, "reason": "the window is filling"}, Compact),
    ("switch_model", {"model": "gpt-5-mini", "reason": "this is mechanical"}, SwitchModel),
    ("tighten_policy", {"mode": "read-only", "reason": "it is thrashing"}, TightenPolicy),
    ("warn_user", {"message": "three tools failed in a row"}, WarnUser),
    ("abort", {"reason": "the same edit four times"}, Abort),
    (
        "propose_instruction",
        {"title": "Run the formatter first", "body": "Always run `just fmt`."},
        ProposeInstruction,
    ),
    (
        "propose_skill",
        {"name": "release-check", "body": "1. just check\n2. just loc"},
        ProposeSkill,
    ),
    ("noop", {"reason": "a long turn, but a correct one"}, Noop),
)


@pytest.mark.parametrize(("action", "fields", "kind"), EIGHT, ids=[a for a, _, _ in EIGHT])
def test_each_whitelisted_action_parses_into_its_own_type(
    action: str, fields: dict[str, object], kind: type
) -> None:
    proposal = parse(fabricate(action=action, **fields), models=MODELS)
    assert isinstance(proposal, kind)


def test_the_eight_cases_above_are_the_whole_whitelist() -> None:
    # So that adding a ninth action to ACTIONS without a test fails here.
    assert tuple(action for action, _, _ in EIGHT) == ACTIONS


def test_an_action_outside_the_whitelist_is_rejected() -> None:
    rejected = parse(fabricate(action="learn", fact="the user prefers tabs"), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "not one of the eight" in rejected.problem


def test_a_proposal_that_loosens_policy_is_rejected_with_its_reason() -> None:
    # An explicit allow does not depend on the current policy to be a widening, so
    # the parser refuses it outright; narrow() decides the comparative cases [CTRL-8].
    rejected = parse(fabricate(action="tighten_policy", rules={"shell": "allow"}), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "never allow" in rejected.problem


def test_a_tighten_policy_proposal_naming_something_that_is_not_a_mode_is_rejected() -> None:
    rejected = parse(fabricate(action="tighten_policy", mode="god-mode"), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "mode must be one of" in rejected.problem


def test_a_tighten_policy_proposal_that_asks_for_nothing_is_rejected() -> None:
    rejected = parse(fabricate(action="tighten_policy", reason="be careful"), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "nothing to tighten" in rejected.problem


def test_a_tighten_policy_proposal_with_only_caveats_is_not_empty() -> None:
    # caveats is the fifth field CTRL-8 added; asking for it alone is enough.
    proposal = parse(fabricate(action="tighten_policy", caveats=["paths=reports/"]), models=MODELS)
    assert isinstance(proposal, TightenPolicy)
    assert proposal.want.caveats == ("paths=reports/",)


def test_a_tighten_policy_proposal_with_a_malformed_caveat_is_rejected() -> None:
    # Validated against the same parser --scope uses, so a bad pair never becomes a
    # proposal at all, the same way a bad mode never does.
    rejected = parse(fabricate(action="tighten_policy", caveats=["nonsense"]), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "KEY=VALUE" in rejected.problem


def test_switch_model_naming_an_arbitrary_model_is_rejected_and_says_what_it_has() -> None:
    # ROUTE-8: the target set is what the project configured, not what a model names.
    rejected = parse(fabricate(action="switch_model", model="gpt-9-omni"), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert "gpt-9-omni" in rejected.problem
    assert "claude-sonnet-4" in rejected.problem


def test_switch_model_is_rejected_when_the_project_configured_nothing() -> None:
    rejected = parse(fabricate(action="switch_model", model="gpt-5-mini"), models=frozenset())
    assert isinstance(rejected, Rejected)
    assert "none" in rejected.problem


@pytest.mark.parametrize("value", [0.05, 0.99, "half", True])
def test_compact_refuses_a_threshold_that_is_not_a_fraction(value: object) -> None:
    rejected = parse(fabricate(action="compact", compact_at=value), models=MODELS)
    assert isinstance(rejected, Rejected)


def test_a_skill_name_that_is_a_path_is_refused_rather_than_cleaned() -> None:
    # It becomes a file name under .edgar/proposals/, and a sanitised name is a
    # name nobody asked for.
    rejected = parse(
        fabricate(action="propose_skill", name="../../etc/passwd", body="x"), models=MODELS
    )
    assert isinstance(rejected, Rejected)
    assert "is not a skill name" in rejected.problem


@pytest.mark.parametrize(
    ("action", "missing"),
    [("warn_user", "message"), ("propose_instruction", "title"), ("propose_skill", "name")],
)
def test_an_action_missing_its_one_required_field_is_rejected(action: str, missing: str) -> None:
    rejected = parse(fabricate(action=action), models=MODELS)
    assert isinstance(rejected, Rejected)
    assert missing in rejected.problem


def test_a_fenced_answer_still_parses() -> None:
    # Small models wrap JSON in a code fence more often than not.
    fenced = '```json\n{"action": "noop", "reason": "nothing to do"}\n```'
    assert isinstance(parse(fenced, models=MODELS), Noop)


@pytest.mark.parametrize("raw", ["", "I think you should stop.", "[1, 2, 3]", "{"])
def test_an_answer_that_is_not_a_json_object_is_rejected_not_raised(raw: str) -> None:
    # Nothing the controller returns may fail the turn, including gibberish [CTRL-11].
    assert isinstance(parse(raw, models=MODELS), Rejected)


def test_a_long_body_is_cut_rather_than_refused() -> None:
    proposal = parse(fabricate(action="warn_user", message="x" * 50_000), models=MODELS)
    assert isinstance(proposal, WarnUser)
    assert len(proposal.message) == 2000


def test_the_switch_model_targets_are_the_route_rules_and_the_role_bindings() -> None:
    models = ModelSection(default="gpt-5", controller="gpt-5-mini")
    rules = (Route(name="cheap", model="llama3.1", role="main"),)
    assert targets(models, rules) == frozenset({"gpt-5", "gpt-5-mini", "llama3.1"})


def test_an_unconfigured_role_contributes_no_target() -> None:
    # A None binding means "the main model", not "some model edgar may pick" [PRV-15].
    assert targets(ModelSection(default="gpt-5"), ()) == frozenset({"gpt-5"})
