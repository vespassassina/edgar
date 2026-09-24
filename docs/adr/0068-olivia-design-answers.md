# ADR-0068 — Olivia: the v5 fork's design answers

**Status:** Accepted · 2026-09-24 · Names the v5 fork and settles the open
questions ADR-0067 left; ADR-0067 moves to Accepted alongside this one.

## Context

ADR-0067 proposed the v5 fork and left several questions open: the name, how
inputs arrive, what the trigger strategy's outcomes are, whether home
routines may be learned, what the governor is, what Jev may decide, which
memory backends are allowed, the policy language, how much the self-learning
strategy may vary, which observability sinks ship first, where the branch
lives, and the size budget. The maintainer answered each in an interview;
this ADR is the record.

## Decisions

**1. Name: Olivia.** PyPI distribution `olivia-agent`, Python package
`olivia`, command `olivia`, tag prefix `olivia-v*`. Checking PyPI and GitHub
for name clashes is still open — do that before the first release, not
before the branch.

**2. Inputs arrive through an inbox, drained by the scheduler tick.**
Anything external — a webhook relay, a mail rule, a Home Assistant automation
— writes a JSONL file into an inbox directory; `edgar schedule tick`'s v4
machinery drains it (ADR-0039). No listener in the agent itself, so nothing
beyond item 3 of ADR-0067 (only the governor decides) needs to be amended
for input to arrive. Latency is bounded by the tick interval, one minute by
default.

**3. The trigger strategy has five outcomes: BUFFER, QUEUE, STEER, REFUSE,
RUN_NOW.**
- BUFFER holds the input and decides again later — coalescing, waiting for
  more context or a quiet session.
- QUEUE starts a new run for it at the next tick.
- STEER injects it into a running session at the loop's one safe point
  (ADR-0028), tainted as outside data (item 5 of ADR-0067).
- REFUSE drops it and records why.
- RUN_NOW jumps the queue: it starts in the same tick that drained it, ahead
  of anything already queued, and past the concurrency cap by one slot. It
  is gated by its own policy rule, and the default policy grants it to
  nothing — an input earns RUN_NOW only when a human wrote a rule saying so.

**4. Home routines may be learned, fully, including presence.** The
maintainer confirmed this after a challenge: it amends the Never list's
"user modelling" and the learning boundary (ADR-0017) on the Olivia line,
beyond the narrower "device events only, disabled by default" option this
ADR's author recommended. On the Olivia line, and there only:
- A learned routine may be applied automatically, not only proposed.
- Presence — who is home, and when — may be stored and used.
- The rule from ADR-0067 item 5 that "nothing on the learning path reads
  tool output, error text, fetched content, piped stdin or `@file`
  attachments" no longer bounds the home routine learner; it may read device
  events, which are none of those things, but it is not limited to them by
  this decision.

  **Consequence, stated plainly:** this is the biggest authority and privacy
  surface on the Olivia line. A model that has modelled when the house is
  empty is a system worth breaking into, and a wrong model that acts ahead
  of people (locks, heating, cameras) is a safety question, not only a
  privacy one. The governor's policy is the only thing standing between this
  amendment and a bad actuation, so the home routine learner ships no earlier
  than the governor does, and the governor's policy for it defaults to deny
  every actuator ADR-0067's use-cases document already lists as denied
  (locks, doors, alarms, cameras, ovens, heating limits) regardless of what
  the routine learner proposes. Revisit this decision if a home incident
  happens in testing, or if a regulator (GDPR, an EU AI Act reading) treats
  presence inference as data the maintainer cannot self-authorize.

**5. The governor is both a local sealed process and a remote service, behind
one protocol.** One governor protocol (request: intent, actor, action,
resource, context → response: allow, deny, reason, receipt); a local adapter
runs it as a separate OS-level process with its own user, holding the policy
and the signing key; a remote adapter calls an HTTP service instead. Olivia
never talks to a governor directly except through this protocol, so an
enterprise can swap the local adapter for their own remote governor without
touching Olivia's code.

**6. Jev is two Decider interfaces, not one: `TriggerDecider` and
`StrategyDecider`.** A user may enable Jev for triggers only, strategy
choice only, both, or neither — each is its own plugin slot with its own
entry point, and turning one on does not turn on the other. Below a
confidence threshold, each falls back to its fixed rule (the trigger
strategy's default refuses; model and reasoning-strategy choice falls back
to the declarative routing rules ADR-0013 already has). Neither interface is
ever called from `decide()`, a ticket or the governor (item 5's "nothing on
the authorisation path is a model" rule is unchanged).

**7. Memory backends: embedded by default, servers allowed as plugins.**
SQLite FTS5 stays the built-in default. Redis, Postgres/pgvector and other
server-backed stores are allowed as third-party `Retriever`/memory adapters,
not built in — an adapter that needs a server needs its own credentials and
network policy, and the governor's policy must name the host before the
adapter may reach it (fail closed, item 3 of ADR-0067).

**8. The governor's policy language is Cedar.** Typed, and its own tool can
prove a policy never allows a given action — which is what a subject caveat
(who an action is for, the gap ADR-0067's use cases found) needs to be
checkable rather than merely readable. Cedar's principal/action/resource/
context shape maps onto the broker's existing caveats (tools, paths, hosts,
calls, until) plus the new subject caveat directly. Cost: a Rust dependency
with Python bindings, the first non-stdlib dependency on the authorisation
path — worth writing down as a real cost, not waved through, because
ADR-0022 chose ports specifically to keep the core free of exactly this kind
of dependency. It is confined to the governor process, local or remote,
never imported by Olivia's own core.

**9. The self-learning strategy is fully pluggable: a strategy may declare
its own sources and destinations, bounded only by the governor.** This
supersedes ADR-0067 item 5's kept rule that a learning strategy "may change
how it learns, never what it reads or where it writes." On the Olivia line,
a strategy may name additional sources (ticket outcomes, eval results, tool
output under a governor-approved caveat) and additional destinations, and
the governor's policy is what stops a strategy from reading or writing
somewhere a human did not approve — the boundary moves from code
(`ADR-0017`'s "enforced by what each function accepts") to policy. Cost: the
learning boundary is no longer provably closed by inspection of the
learning package alone; auditing it means reading the policy too.

**10. Observability ships with two sinks: the existing JSONL event tap, and
an OpenTelemetry exporter as a plugin.** `--events` keeps working unchanged;
the OTel exporter sends the same events as spans to whatever collector an
enterprise already runs. A terminal live view and governor-receipts-only
were both considered and deferred, not rejected — either can be added later
as its own plugin without touching this decision.

**11. The line lives on a long-lived branch, `olivia`, in this repository.**
Main (edgar 4.x) merges into `olivia` after each edgar release; `olivia`
never merges back into main. Olivia-only docs live under `docs/olivia/`
(moved there from `docs/v5/` in the same commit that creates the branch).

**12. Budget: 20,000 lines of code, the removable-tier rule kept.** Olivia's
own code — the governor client, the pluggable strategies, the inbox, the
trigger strategy, the home routine learner — lives in new removable
packages (`olivia.governor`, `olivia.strategy`, `olivia.trigger`, …), the
same shape ADR-0015/ADR-0057 use for v3 and v4. Core, v1 and v2 stay at
≤ 9,500 lines of code outside the removable packages; the 20,000 ceiling is
Olivia's own packages plus everything edgar already carries.

**13. First milestone: the governor, and fail-closed autonomy, before
anything else.** Nothing that runs without a human watching lands before the
thing that would have refused it. Order after that: the inbox and trigger
strategy, then the pluggable strategy and memory ports, then the home
routine learner last, since it carries the largest amendment and needs the
governor's deny-by-default policy already proven in the milestone before it.

## Consequences

- ADR-0067 moves from Proposed to Accepted; its numbered decisions stand
  except where this ADR names a supersession (items 4 and 9 above).
- The Never list amendment for "user modelling" is now real, not
  hypothetical, and it is the largest single departure this fork makes from
  edgar's own rules. It is scoped to the Olivia line only, gated by the
  governor, and denies every physical actuator by default regardless of what
  is learned.
- Before any Olivia code: a tier ADR (this fork's own milestone list, sized
  against the 20,000-line budget) and a PRD with acceptance criteria, per
  the maintainer's design → spec → plan → test order. This ADR is the design
  step; those are next.
- `AGENTS.md` on the Olivia line needs the maintainer's own hand-edit
  (ADR-0007, ADR-0008); no agent may write it, on this line or any other.
