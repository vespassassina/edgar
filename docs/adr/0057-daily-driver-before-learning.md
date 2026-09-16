# ADR-0057 — The daily driver comes before learning: v2, v3, v4

**Status:** Accepted · 2026-09-16 · Supersedes the tier *contents* and the v2
budget in ADR-0015; assigns ADR-0052's media input to a milestone; amends PRD
§5.1, §5.3, §6, §11 and the roadmap

## Context

v1.0 is code-complete at exactly 8,000 of 8,000 lines of code, with 670 tests
passing ([ADR-0056](0056-m11-as-built.md)). The review that followed it found
three things.

First, the tool has never been used. Every test runs against the fake provider;
the cassettes are synthetic except Ollama's; nobody has run a session on a real
model, and the maintainer, who is the first user, has not worked a day in it.
PRD §2's third outcome, "a tool Diego uses daily", has no evidence either way.

Second, what daily work needs is mostly the list ADR-0050 and ADR-0053 cut to
make the budget: `@path` attachments, plan mode and the `todo` tool, worktree
isolation for write-capable subagents, a sandboxed shell, `sessions compact`,
`context show`, the rest of `doctor`, `route explain`, `agents list|validate`,
`ext validate|add`, `config show --resolved`, the contract kit, `skills audit`.
Plus two gaps that were never in any tier: web search (there is `fetch`, there
is no search) and git as anything more than `shell`. Plus images (ADR-0052,
"awaiting a slot").

Third, the tier that ADR-0015 planned next, v2 = learning, controller, synthesis,
escalation, broker, scheduling, learns from corrections and verified runs. With
no daily use there is nothing to learn from, and no way to know whether the
synthesis triggers fire on real work. Building the learning layer on an unused
tool would repeat the mistake ADR-0015 was written to avoid: shipping the
interesting parts before the useful ones.

What makes this non-obvious is that ADR-0015's v2 is not wrong. Its packages,
its seam and its removability rule are all good and stay. The question is order,
and whether a tier that adds to Core and v1 packages, and so is not removable,
can sit in front of the one that is.

## Options

**A. Build ADR-0015's v2 as planned.** Learning next, the daily-driver items
folded in where they fit. Keeps the roadmap stable. Costs the same thing it cost
last time: the useful parts get squeezed by the interesting ones, and the
learning layer is tuned against synthetic runs.

**B. The daily driver as its own tier, first.** A new v2 holds everything a
person needs to work in edgar all day. ADR-0015's v2 becomes v3 (learning and the
controller) and v4 (broker and scheduling: the parts that run unattended). Each
tier keeps a fixed budget. Costs a renumbering that touches every document, and
a v2 that is not removable, since it extends Core and v1 packages.

**C. No new tier: put the daily-driver items in v1.1 point releases.** Smallest
change on paper. Rejected because v1's budget is spent to the line; every item
would need a matching cut, and "v1 ≤ 8,000" would stop being true in practice
while staying true in the docs.

## Decision

Option B.

| Tier | Name | Milestones | Promise | Budget |
|---|---|---|---|---|
| **Core** (0.x) | | M0–M6 | Read it in an afternoon, use it every day | ≤ 5,000 LOC |
| **v1** (1.0) | | M7–M11 | Extensible and remembers; extension formats frozen | ≤ 8,000 LOC |
| **v2** (2.0) | the daily driver | M18–M22 | Work in it all day: code, git, subagents, tools, search, images | ≤ 9,500 LOC |
| **v3** (3.0) | learning | M12–M15 | Learns from what you type and what breaks; removable | ≤ 12,000 LOC |
| **v4** (4.0) | unattended | M17, M16 | Runs unattended under a signed scope; removable | ≤ 13,000 LOC |

**1. Milestone IDs keep their numbers.** M12–M17 stay what ADR-0015 made them.
The daily driver gets new numbers, M18–M22, and the order of work is stated in
the roadmap, as it was when M4 went before M3 ([ADR-0033](0033-replan-after-m2.md)).

**2. v2 is not removable, and says so.** Its code lives in Core and v1 packages
(`cli/`, `context/`, `tools/`, `agents/`, `sandbox/`, `core/message.py` for
`ImageBlock`). NFR-12's rule, "deleting the removable packages leaves a working
suite", is unchanged in substance and now names v3 and v4: `edgar.learning`,
`edgar.controller`, `edgar.schedule`, `edgar.broker`, `providers/escalation.py`.
Nothing in Core, v1 or v2 imports them. The budget helper's `V2_PATHS` becomes
`REMOVABLE_PATHS`, and the "without removable packages" limit is checked against
the v2 budget from M12 on.

**3. v2 has five milestones, and the first one writes no code.** M18 is the
teaching layer for v1 that M11 owed: a tour page per v1 feature, Core's own
missing stops, a test that no source file is without a stop, and the map. It
comes first because the daily-driver milestones each end with a tour delivery,
and that discipline needs the pages to exist. M19 working state, M20 seeing and
searching (images, web search, git), M21 isolation (worktrees, sandboxes), M22
inspection commands and the 2.0 release. Each is broken down in the roadmap to
the level of files, requirement IDs and tests, so a coding session can take one
item at a time.

**4. Every milestone ends with its tour.** A milestone's last item is always the
tour page or stops for what it built, in the same format Core's tour uses
(stages, stops, look-for hints, a diagram, a size table), and `test_tour.py`'s
no-orphan check keeps it honest. A milestone with code and no tour is not done.

**5. Media input goes in M20** (ADR-0052 decision 1 said "when v2 is planned";
this is that).

**6. Web search and git are extensions, not code.** An HTTP tool for a search
API with the host fixed and the key from the environment (Brave, Tavily or a
self-hosted SearXNG, the user's choice, never a default host: PRV-15), a set of
command tools wrapping `git`, and a `git` skill for commit and branch etiquette.
They ship in `examples/` with Cookbook recipes and cost zero lines of `src/`.
This is what EXT-10's freeze was for.

**7. Budgets.** v2 adds at most 1,500 lines of code to v1's 8,000, estimated at
about 1,250 (see the roadmap's table). v3 adds 2,500 (ADR-0015 planned 3,000 for
the whole of its v2; the broker and scheduling moving out is what pays for the
difference). v4 adds 1,000. The budgets are constraints, not estimates, as before:
if a milestone does not fit, something moves later, the number stays.

**8. The done test for v2 is use, not a checklist.** 2.0 ships when the
maintainer has worked in edgar on edgar for two weeks with a real model and the
journal lists no blocking friction, and when the two human criteria of PRD §11
that v1 left open have been done by an actual outside person. Daily use is how
the second one gets an opportunity.

## Consequences

- **Load-bearing: the order.** M18 first, because every later milestone's tour
  needs it; the dogfood week before M19, because the friction list is M19–M22's
  real specification and the roadmap items are the best guess without it.
- **v1.0 is tagged before any of this.** The version is still `0.1.0`; the
  `pyapp` and `docker` release jobs have never run. Tagging is a task in the
  handoff, not a milestone.
- **Every document that says "v2" and means learning is amended** in this change:
  PRD §5.1 (tier bullets and the requirement map, now five columns), §5.3, §6
  journey headings, §7.16, §11; BLUEPRINT's tier markers, seam paragraph, port
  table, package tree and section headings; ROADMAP entire; the tour's Part III;
  README's status and tier table; `tests/support/budget.py`'s tier table and
  `TARGET_TIER`. `AGENTS.md` rule 10 and its size table also say v2 and are
  hand-authored: the proposed diff is in the handoff, for the maintainer.
- **"Past v2" becomes "Past v4"**, minus web search and git tools, which are now
  M20, and minus notifications, which go to v4 as a `session_end` deliverable.
- **Semver meaning is unchanged** from ADR-0015: 2.0, 3.0 and 4.0 add to the
  frozen formats and do not change them. `ImageBlock` is an addition to the
  message vocabulary and to the `--events` shape, not a change.
- **The tour grows from one page to a set.** `docs/tour/index.html` stays the
  entry and the Core tour; feature tours are sibling pages sharing its CSS and
  the same `<article class="stop" data-files=…>` shape so one test covers all.
- **Unpleasant:** four tier numbers instead of three, and a v2 that a reader of
  ADR-0015 will expect to be removable and is not. The names in the table exist
  so that "the daily driver" and "the removable tiers" can be said without a
  number.

## Rejected alternatives

**A (learning next)** is rejected until the tool has been used. What would change
the answer: a month of real use showing that the missing pieces are not the ones
listed here but the learning ones, that is, the maintainer reaching for
`/remember` and corrections far more than for plan mode or git. Then M19–M22
shrink and M12 moves up.

**C (point releases)** is rejected because it breaks the budget rule quietly.
What would change the answer: nothing; a budget that is exceeded needs a tier,
not a minor version.

**Renumbering M12–M17 to follow the new v2** was considered and rejected for
the same reason ADR-0015 kept requirement IDs: every ADR, journal entry and
tour stop cites them.
