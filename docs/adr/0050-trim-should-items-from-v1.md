# ADR-0050 — Move v1's `(Should)` items to v2 before building M9–M11

**Status:** Accepted · 2026-09-14

## Context

v1's budget is fixed at 8,000 lines of code (ADR-0015) and does not move; the rule
in `AGENTS.md` is "if a milestone pushes its tier over budget, something moves to a
later tier." At the start of this work, `src/` measured 6,856 of 8,000: 1,144 lines
left for the whole of M9 (subagents, routing, fallback, plan mode), M10
(extensions, hooks, plugins, sandbox, skill audit, embedding API) and M11 (init,
doctor, docs, release automation).

Reference points from milestones already built: `auth/` (OAuth sign-in alone) cost
317 lines of code; `memory/store.py` (facts, undo, FTS5) is 266. M9 through M11 as
fully specced describe several subsystems each at least that size — subagent
fan-out with a cycle guard is one, a four-backend sandbox port is another, a full
skill-audit command with conformance and danger rules is a third. Attempting all of
it at full fidelity was never going to fit; the only question was which parts to
cut and how the decision gets made, not whether one is needed.

The roadmap already marks four items `*(Should)*` rather than `Must`, meaning the
spec itself anticipated some of them not making the cut:

- **SUB-11** — `isolation: worktree` for write-capable subagents (M9)
- **PERM-15** — sandbox backends beyond `none` (`bwrap`, `seatbelt`, `container`) (M10)
- **SKL-18** — `edgar skills audit` (M10)
- **CTX-10** — `edgar sessions compact ID` outside the REPL (M11)

## Options

**A. Build to full spec and let the budget test fail until it's trimmed
reactively.** Keeps every requirement's tier as originally written until a
specific commit can't land. Costs nothing to decide now, but means discovering the
shortfall mid-milestone, after code and tests for the cut item already exist —
wasted work, and a worse position to decide from than doing the arithmetic first.

**B. Trim the `(Should)` items now, before writing any M9–M11 code, and move them
to v2 with this ADR.** The roadmap's own priority markers already say which four
items are first to go if something has to give. Trimming them up front means every
line of code written for M9–M11 from here on is scoped against a budget that's
actually achievable, and the requirement IDs move as a deliberate, documented
choice rather than an emergency cut discovered by a failing test.

**C. Revise the 8,000-line v1 cap instead of cutting scope.** Would let all four
items stay in v1. Rejected for this pass: the cap is the project's one
uncompromising anti-scope-creep mechanism (ADR-0015), and raising it to fit
whatever gets built defeats its purpose. It's not ruled out forever — see
"Rejected alternatives" below — but it is not this decision.

## Decision

Move SUB-11, PERM-15, SKL-18 and CTX-10 from v1 to v2, effective for the M9–M11
work starting now. Concretely:

- `agents/spawn.py` (M9) runs every subagent in the parent's own working copy.
  Parallel write-capable subagents share it; a future `isolation: worktree` (v2)
  is what removes that restriction, not something M9's design needs to leave room
  for beyond not fighting it.
- `shell.sandbox` (`config/schema.py`, `ShellSection`) keeps its `none | bwrap |
  seatbelt | container` type as already shipped, since PERM-15's schema is cheap
  and already Core; only the `bwrap`, `seatbelt` and `container` *implementations*
  move to v2. `none` stays the only backend that actually runs anything. `edgar
  doctor` (M11) does not recommend a backend, since there is nothing yet to
  recommend.
- `edgar skills audit` (SKL-18) does not ship in 1.0. `edgar ext add` (EXT-3)
  still copies a skill in without auditing it first; the conformance and danger
  checks it would have run stay manual (read the skill before copying it) until
  v2.
- `edgar sessions compact ID` (CTX-10) does not ship in 1.0. `/compact` inside the
  REPL (already Core) is unaffected; only the outside-the-REPL, stored-session
  variant is deferred.

PRD §5.1's tier map and requirement table, and `docs/ROADMAP.md`'s M9–M11
sections, are updated in the same change as this ADR to show these four IDs under
v2 rather than v1.

## Consequences

- v1's real remaining budget for M9–M11 is spent on Must-only scope. That is still
  tight against 1,144 lines of code (load-bearing: if it is not enough even after
  this cut, the next lever is moving a whole milestone's Must items to a later
  point in the v1 series, or revisiting Option C — not silently shipping a smaller
  version of a Must requirement without a further ADR).
- Four capabilities readers may expect from "extensible and remembers" don't ship
  at 1.0: worktree-isolated subagents, sandboxed shell execution, a skill vetting
  command, and out-of-REPL session compaction. Each is a real gap, not a rounding
  error, and each is named in `docs/JOURNAL.md`'s open items so it isn't lost.
- Nothing about this changes v1's other Must requirements' shape or interfaces;
  the four moved items were additive on top of already-Must scaffolding (the
  sandbox *type* stays, skill audit was always going to sit beside `ext add`
  rather than inside it, worktree isolation was always an option on top of
  `agents/spawn.py`, not a prerequisite for it), so none of this forces a redesign
  of what does ship.

## Rejected alternatives

Option C (raise the cap) is the one most likely to be revisited. If, after
building M9–M11's Must-only scope, the actual measured cost still doesn't leave
room for a majority of v1's other Must requirements — not just these four
Shoulds — that's a sign the 8,000-line budget itself, not just this session's
scope, was set too low for what v1 promises, and raising it becomes a decision
for the maintainer to make deliberately rather than something a single session's
time pressure should decide.
