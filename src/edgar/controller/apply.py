"""What actually happens when a proposal is accepted [CTRL-6, CTRL-7, CTRL-10, CTRL-12]."""

# One function per action, and one log row per call, so "what did the controller do"
# and "what is in the log" cannot drift apart.
#
# The eight split three ways, and the split is the safety argument:
#
#   compact, switch_model         persist, so they are dry-run by default [CTRL-6]
#   tighten_policy, abort,        act now and end with the session: nothing outlives
#   warn_user, noop               the process, so there is nothing to dry-run
#   propose_instruction,          write a file under .edgar/proposals/ and stop.
#   propose_skill                 They are never "applied", in any mode
#
# `dry_run` therefore governs exactly the first pair. tighten_policy is not in it on
# purpose: CTRL-8 guarantees the change can only make the session stricter, and a
# tightening that waits for a human to approve it is a tightening that does not
# happen. It is still logged, and it still dies with the session.
#
# Nothing here can write a hand-authored file. propose_instruction produces a
# Markdown file in the machine-owned directory (PRD §9.5) that says what to add and
# leaves the adding to a person [CTRL-12]. edgar does not write that file, and does
# not name it either: which file your instructions live in is your decision, and a
# path this code never spells is a path it can never open.

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from edgar.controller.proposals import (
    Abort,
    Compact,
    Noop,
    Proposal,
    ProposeInstruction,
    ProposeSkill,
    SwitchModel,
    TightenPolicy,
    WarnUser,
)
from edgar.controller.store import Controls, Mutation
from edgar.controller.tighten import Narrowing, narrow
from edgar.permissions.policy import Policy

PROPOSALS = ".edgar/proposals"  # machine-owned, per PRD §9.5

# What `abort` asks for. read-only is the last stop on MODES, so narrow() accepts it
# from anywhere and no policy can refuse it.
READ_ONLY = Narrowing(mode="read-only")


@dataclass(frozen=True, slots=True)
class Outcome:
    """What the gate announces and what `edgar controller log` shows."""

    state: str  # proposed | applied | rejected
    message: str
    action: str = "noop"
    mutation_id: int = 0
    policy: Policy | None = None  # a tightened policy, for the guard to adopt


@dataclass(frozen=True, slots=True)
class Site:
    """Where an apply happens: the log, the project, and the live policy. Passed as
    one value so each handler takes two arguments and stays readable."""

    store: Controls
    root: Path
    policy: Policy
    dry_run: bool = True


def apply(proposal: Proposal, site: Site) -> Outcome:
    """Carry out one proposal, log it, and say what happened [CTRL-7]."""
    # Eight branches and no table, unlike proposals.py's BUILDERS. The difference is
    # that each of these takes its own type: a dict keyed on the class would hand
    # every handler a bare `Proposal` and need a cast in all eight to get it back.
    # Nothing here raises; a handler that cannot act returns a rejected Outcome, so
    # nothing the controller does can fail the turn [CTRL-11].
    if isinstance(proposal, Compact):
        return _compact(proposal, site)
    if isinstance(proposal, SwitchModel):
        return _switch_model(proposal, site)
    if isinstance(proposal, TightenPolicy):
        return _tighten_policy(proposal, site)
    if isinstance(proposal, Abort):
        return _abort(proposal, site)
    if isinstance(proposal, WarnUser):
        return _warn_user(proposal, site)
    if isinstance(proposal, ProposeInstruction):
        return _propose_instruction(proposal, site)
    if isinstance(proposal, ProposeSkill):
        return _propose_skill(proposal, site)
    return _noop(proposal, site)


def _log(site: Site, action: str, detail: str, state: str, reason: str, after: str = "") -> int:
    return site.store.record(Mutation(0, time.time(), action, detail, "", after, state, reason))


def _persisted(action: str, detail: str, after: str, reason: str, site: Site) -> Outcome:
    # The shared shape of the two that outlive the session: dry-run says what would
    # have changed, and a later `edgar controller apply ID` turns the row into one
    # that overrides() reads [CTRL-6, CTRL-10].
    state = "proposed" if site.dry_run else "applied"
    said = f"would have {detail}" if site.dry_run else detail
    return Outcome(state, said, action, _log(site, action, detail, state, reason, after))


def _compact(p: Compact, site: Site) -> Outcome:
    detail = f"compact from {p.compact_at:.0%} of the window instead"
    return _persisted("compact", detail, f"{p.compact_at:.4f}", p.reason, site)


def _switch_model(p: SwitchModel, site: Site) -> Outcome:
    return _persisted("switch_model", f"run on {p.model}", p.model, p.reason, site)


def _tighten_policy(p: TightenPolicy, site: Site) -> Outcome:
    # narrow() is the only judge. A string back means it tried to loosen something,
    # and a refused tightening is logged in the rejected table, not the mutation log:
    # nothing changed, so there is nothing to revert [CTRL-8].
    tightened = narrow(site.policy, p.want)
    if isinstance(tightened, str):
        site.store.reject(p.want.to_json(), tightened)
        return Outcome("rejected", f"refused: {tightened}", "tighten_policy")
    detail = f"tightened policy: {p.want.to_json()}"
    mutation = _log(site, "tighten_policy", detail, "applied", p.reason)
    return Outcome("applied", detail, "tighten_policy", mutation, tightened)


def _abort(p: Abort, site: Site) -> Outcome:
    # The turn already finished, so there is nothing left to stop. What abort does
    # is take the session's hands away: read-only for the rest of it, in memory
    # only. It is the strictest mode, so narrow() can never refuse it.
    tightened = narrow(site.policy, READ_ONLY)
    detail = f"stopped acting: read-only for the rest of the session ({p.reason})"
    mutation = _log(site, "abort", detail, "applied", p.reason)
    policy = tightened if isinstance(tightened, Policy) else site.policy
    return Outcome("applied", detail, "abort", mutation, policy)


def _warn_user(p: WarnUser, site: Site) -> Outcome:
    return Outcome(
        "applied", p.message, "warn_user", _log(site, "warn_user", p.message, "applied", p.reason)
    )


def _noop(p: Noop, site: Site) -> Outcome:
    # Logged anyway. "The controller looked and decided nothing was wrong" is the
    # answer to a question people ask of the log, and silence does not give it.
    detail = p.reason or "nothing worth changing"
    return Outcome("applied", detail, "noop", _log(site, "noop", detail, "applied", p.reason))


def _propose_instruction(p: ProposeInstruction, site: Site) -> Outcome:
    body = f"# {p.title}\n\n{p.body}\n\n> Why: {p.reason or 'no reason given'}\n"
    return _proposal_file(site, "propose_instruction", _slug(p.title), body, p.reason)


def _propose_skill(p: ProposeSkill, site: Site) -> Outcome:
    # M13 writes the proposal and stops. Turning one into a real skill file is
    # M14's (SKL-8..16); there is no `skills.synthesis` setting to honour yet.
    body = f"---\nname: {p.name}\n---\n\n{p.body}\n\n> Why: {p.reason or 'no reason given'}\n"
    return _proposal_file(site, "propose_skill", f"skill-{p.name}", body, p.reason)


def _proposal_file(site: Site, action: str, slug: str, body: str, reason: str) -> Outcome:
    # The id comes first so the file is named after its own log row: `edgar
    # controller apply 7` and `.edgar/proposals/7-*.md` are the same thing.
    mutation = _log(site, action, "written for you to read", "proposed", reason)
    path = site.root / PROPOSALS / f"{mutation}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    shown = path.relative_to(site.root).as_posix()
    site.store.set_after(mutation, shown)
    return Outcome("proposed", f"wrote {shown}; nothing was changed for you", action, mutation)


def _slug(title: str) -> str:
    kept = "".join(c if c.isalnum() else "-" for c in title.lower())
    return "-".join(part for part in kept.split("-") if part)[:40] or "instruction"


def revert(store: Controls, mutation_id: int) -> str:
    """Undo one row of the log by id, the way `edgar memory undo` does [CTRL-10]."""
    # 1. There has to be a row, and it has to be one that is in force.
    mutation = store.mutation(mutation_id)
    if mutation is None:
        return f"no mutation {mutation_id}"
    if mutation.state != "applied":
        return f"mutation {mutation_id} is {mutation.state}, not applied"
    # 2. Reverting is one state change. overrides() stops returning the row, so the
    #    next session falls back to what config.toml says, which is the only other
    #    answer there has ever been [CTRL-6].
    store.set_state(mutation_id, "reverted")
    return f"reverted {mutation_id}: {mutation.detail}"


def approve(store: Controls, mutation_id: int) -> str:
    """Turn a dry run into the real thing, by hand [CTRL-6, CTRL-10]."""
    mutation = store.mutation(mutation_id)
    if mutation is None:
        return f"no mutation {mutation_id}"
    if mutation.state != "proposed":
        return f"mutation {mutation_id} is {mutation.state}, not proposed"
    # A written proposal is the deliverable, not a step towards one: applying it
    # means a person reads the file and edits their own instructions [CTRL-12].
    if mutation.action.startswith("propose_"):
        return f"{mutation.after or 'the proposal'} is for you to apply by hand"
    store.set_state(mutation_id, "applied")
    return f"applied {mutation_id}: {mutation.detail}"
