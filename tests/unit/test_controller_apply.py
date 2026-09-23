"""Applying a proposal: dry run, log, revert [CTRL-6, CTRL-7, CTRL-10, CTRL-12].

Every proposal here is fabricated by hand. What is being tested is what edgar does
with one, which is the half that touches the disk and the live policy — so this file
also holds the two assertions the roadmap asks for by name, that a loosening and an
arbitrary model are rejected *and logged*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.controller.apply import Site, apply, approve, revert
from edgar.controller.proposals import (
    Abort,
    Compact,
    Noop,
    Proposal,
    ProposeInstruction,
    ProposeSkill,
    Rejected,
    SwitchModel,
    TightenPolicy,
    WarnUser,
    parse,
)
from edgar.controller.store import Controls
from edgar.controller.tighten import Narrowing
from edgar.permissions.policy import Policy


@pytest.fixture
def site(tmp_path: Path) -> Site:
    policy = Policy(mode="auto", cwd=tmp_path, home=tmp_path, write_paths=("./**", "./src/**"))
    return Site(Controls(tmp_path / ".edgar" / "controller.db"), tmp_path, policy)


# All eight, with a fabricated proposal each, against a real store and a real path.
EIGHT: tuple[tuple[str, Proposal], ...] = (
    ("compact", Compact(0.5, "the window is filling")),
    ("switch_model", SwitchModel("gpt-5-mini", "this is mechanical")),
    ("tighten_policy", TightenPolicy(Narrowing(mode="ask"), "it is thrashing")),
    ("warn_user", WarnUser("three tools failed in a row")),
    ("abort", Abort("the same edit four times")),
    ("propose_instruction", ProposeInstruction("Run the formatter", "Always `just fmt`.")),
    ("propose_skill", ProposeSkill("release-check", "1. just check")),
    ("noop", Noop("a long turn, but a correct one")),
)


@pytest.mark.parametrize(("action", "proposal"), EIGHT, ids=[a for a, _ in EIGHT])
def test_every_action_is_carried_out_and_leaves_exactly_one_row(
    action: str, proposal: Proposal, site: Site
) -> None:
    outcome = apply(proposal, site)
    assert outcome.action == action
    assert outcome.message
    rows = site.store.mutations()
    assert [(row.action, row.id) for row in rows] == [(action, outcome.mutation_id)]


@pytest.mark.parametrize(("action", "proposal"), EIGHT, ids=[a for a, _ in EIGHT])
def test_no_action_ever_writes_outside_the_machine_owned_directory(
    action: str, proposal: Proposal, site: Site
) -> None:
    # The whole point of CTRL-12: a proposal is a file under .edgar/, never an edit
    # to something a human wrote. Nothing else in the project may appear.
    apply(proposal, site)
    written = sorted(
        p.relative_to(site.root).as_posix() for p in site.root.rglob("*") if p.is_file()
    )
    assert all(path.startswith(".edgar/") for path in written), written


def test_a_persisted_action_is_a_dry_run_by_default_and_overrides_nothing(site: Site) -> None:
    outcome = apply(Compact(0.5, "why"), site)
    assert outcome.state == "proposed"
    assert outcome.message.startswith("would have")
    assert site.store.overrides() == {}


def test_approving_a_dry_run_by_hand_is_what_makes_it_take_effect(site: Site) -> None:
    outcome = apply(SwitchModel("gpt-5-mini", "why"), site)
    assert "applied" in approve(site.store, outcome.mutation_id)
    assert site.store.overrides() == {"switch_model": "gpt-5-mini"}


def test_dry_run_off_applies_straight_away(site: Site) -> None:
    live = Site(site.store, site.root, site.policy, dry_run=False)
    apply(Compact(0.45, "why"), live)
    assert site.store.overrides() == {"compact": "0.4500"}


def test_reverting_a_mutation_takes_the_override_away(site: Site) -> None:
    live = Site(site.store, site.root, site.policy, dry_run=False)
    outcome = apply(SwitchModel("gpt-5-mini", "why"), live)
    assert site.store.overrides()
    assert "reverted" in revert(site.store, outcome.mutation_id)
    assert site.store.overrides() == {}


def test_the_newest_applied_row_of_a_kind_is_the_one_in_force(site: Site) -> None:
    live = Site(site.store, site.root, site.policy, dry_run=False)
    apply(Compact(0.60, "first"), live)
    apply(Compact(0.40, "second"), live)
    assert site.store.overrides() == {"compact": "0.4000"}


def test_reverting_twice_is_refused_rather_than_silently_repeated(site: Site) -> None:
    live = Site(site.store, site.root, site.policy, dry_run=False)
    outcome = apply(Compact(0.5, "why"), live)
    revert(site.store, outcome.mutation_id)
    assert "not applied" in revert(site.store, outcome.mutation_id)


def test_reverting_a_mutation_that_is_not_there_says_so(site: Site) -> None:
    assert revert(site.store, 41) == "no mutation 41"


def test_a_tightening_takes_effect_now_and_is_not_a_dry_run(site: Site) -> None:
    # It can only make the session stricter, so waiting for approval would mean the
    # tightening never happens [CTRL-8].
    outcome = apply(TightenPolicy(Narrowing(mode="ask"), "why"), site)
    assert outcome.state == "applied"
    assert outcome.policy is not None and outcome.policy.mode == "ask"


def test_a_proposal_that_loosens_policy_is_rejected_and_logged(site: Site) -> None:
    # The roadmap's second "done when": rejected, and visible afterwards.
    loosening = TightenPolicy(Narrowing(mode="yolo"), "let me work")
    outcome = apply(loosening, site)
    assert outcome.state == "rejected"
    assert site.store.mutations() == []
    logged = site.store.rejections()
    assert len(logged) == 1 and "looser" in logged[0][3]


def test_a_caveats_tightening_attenuates_the_sessions_live_ticket(site: Site) -> None:
    # CTRL-8's fifth field, applied through the same attenuate() `task` uses on
    # delegation, not a new merge function [ADR-0039].
    from edgar.broker.guard import TicketGuard
    from edgar.broker.ticket import Ticket

    guard = TicketGuard(Ticket(intent_id="i1"))
    live = Site(site.store, site.root, site.policy, dry_run=False, broker=guard)
    outcome = apply(TightenPolicy(Narrowing(caveats=("paths=reports/",)), "narrowing"), live)
    assert outcome.state == "applied"
    assert {c.kind: c.value for c in guard.ticket.caveats} == {"paths": "reports/"}


def test_a_caveats_tightening_with_no_ticket_this_session_is_rejected_and_logged(
    site: Site,
) -> None:
    outcome = apply(TightenPolicy(Narrowing(caveats=("paths=reports/",)), "narrowing"), site)
    assert outcome.state == "rejected"
    logged = site.store.rejections()
    assert len(logged) == 1 and "no ticket" in logged[0][3]


def test_a_switch_model_naming_an_arbitrary_model_is_rejected_and_logged(site: Site) -> None:
    # It never becomes a proposal, so the rejection is the parser's and the log is
    # the rejected table. Same outcome, one step earlier [ROUTE-8].
    rejected = parse(
        '{"action": "switch_model", "model": "gpt-9-omni"}', models=frozenset({"gpt-5"})
    )
    assert isinstance(rejected, Rejected)
    site.store.reject(rejected.raw, rejected.problem)
    logged = site.store.rejections()
    assert len(logged) == 1 and "gpt-9-omni" in logged[0][3]


def test_abort_takes_the_session_read_only(site: Site) -> None:
    outcome = apply(Abort("enough"), site)
    assert outcome.policy is not None and outcome.policy.mode == "read-only"
    assert outcome.state == "applied"


def test_a_written_proposal_names_its_own_log_row(site: Site) -> None:
    outcome = apply(ProposeInstruction("Run the formatter first", "Always `just fmt`."), site)
    written = sorted((site.root / ".edgar" / "proposals").iterdir())
    assert [p.name for p in written] == [f"{outcome.mutation_id}-run-the-formatter-first.md"]
    assert "Always `just fmt`." in written[0].read_text(encoding="utf-8")


def test_applying_a_written_proposal_hands_it_back_to_the_human(site: Site) -> None:
    # CTRL-12: there is no mode in which edgar edits the instructions file itself.
    outcome = apply(ProposeInstruction("Do the thing", "Body."), site)
    answer = approve(site.store, outcome.mutation_id)
    assert "for you to apply by hand" in answer
    assert site.store.mutation(outcome.mutation_id) is not None
    assert site.store.mutations()[0].state == "proposed"


def test_a_skill_proposal_is_a_file_and_never_a_skill(site: Site) -> None:
    apply(ProposeSkill("release-check", "1. just check"), site)
    written = sorted((site.root / ".edgar" / "proposals").glob("*.md"))
    assert len(written) == 1 and "skill-release-check" in written[0].name
    assert not (site.root / ".edgar" / "skills").exists()


def test_the_log_reads_newest_first(site: Site) -> None:
    apply(Noop("one"), site)
    apply(Noop("two"), site)
    assert [row.reason for row in site.store.mutations()] == ["two", "one"]


def test_nothing_is_on_disk_until_there_is_something_to_store(tmp_path: Path) -> None:
    # storage/db.py's rule, inherited: an empty project has no controller.db.
    store = Controls(tmp_path / ".edgar" / "controller.db")
    assert store.mutations() == [] and store.overrides() == {}
    assert not store.path.exists()
