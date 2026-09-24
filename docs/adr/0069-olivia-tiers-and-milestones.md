# ADR-0069 — Olivia's tier: layout, seams, budget and milestones

**Status:** Proposed · 2026-09-24 · The tier ADR that ADR-0067 and ADR-0068
require before any Olivia code; on the `olivia` line only

## Context

ADR-0067 forks Olivia onto the `olivia` branch. ADR-0068 sets its design:
a governor behind one protocol, Cedar policy, inbox input, five trigger
outcomes, two Decider slots, pluggable strategies, memory and learning,
OpenTelemetry, home routines, a 20,000-line ceiling and the order governor
first, home last. Neither says where the code lives, how it attaches to
edgar, what the budget buys per milestone, or how Olivia releases without
tripping edgar's release. Five facts from the code make this non-obvious:

1. **Outside the removable packages there are 3 lines of code left**
   (9,497 of 9,500). ADR-0068 §12 keeps that cap. Any seam Olivia needs in
   Core, v1 or v2 code has to be paid for there.
2. **Half the governor's seam exists.** `permissions/guard.py` takes an
   `Asker`, and `edgar.run()` already passes one through. Every Ask can go to
   the governor today. What cannot is an engine Allow: the guard never asks
   anyone about those, and ADR-0067 item 3 says the governor decides every
   action the policy covers, not just the ones edgar would have prompted for.
3. **The `pre_tool` vetoes can only refuse** (ADR-0039). That is right for
   the broker and wrong for the governor, which replaces a human and has to
   be able to answer Ask with allow.
4. **`/steer` is in-process** (`cli/slash.py` calls `session.steer()`), and
   a scheduled run is too (`schedule/run.py` calls `run_prompt`). An inbox
   STEER arrives in a later `tick` process, not the one running the session.
5. **`release.yml` runs on any published GitHub release**, not on a tag
   pattern. It publishes whatever `pyproject.toml` names at the tagged
   commit, and pushes a `ghcr.io/…/edgar` image.

## Options

**Layout.**

**A. Rename `edgar` to `olivia` on the branch.** One package, one name. Every
merge from `main` becomes a rename merge across 236 files, the exact cost
ADR-0067 accepted only for `AGENTS.md`, the PRD, the roadmap and the budget
file.

**B. Keep `src/edgar/` byte-for-byte and add `src/olivia/` beside it.**
Merges from `main` stay clean. The `olivia-agent` distribution ships both
packages, so it cannot be installed into the same environment as
`edgar-harness`. `uvx`, `pipx` and the binaries isolate anyway.

**The governor's seam.**

**C. The governor as an `Asker` plus a `pre_tool` veto.** No new seam, but
two calls for an Ask (veto, then asker), and a veto that runs before the
engine, so it cannot see the engine's decision.

**D. A `governor` slot on `Guard`, consulted after `decide()`.** One call per
tool call, with the engine's decision in hand. It costs about 10 lines of
code in `permissions/guard.py`, a non-removable file.

## Decision

**B and D.**

1. **Layout.** `src/edgar/` is edgar 4.x and changes on this line only
   through the seams listed in item 3. Olivia's code is `src/olivia/`, in
   removable packages: `olivia.governor`, `olivia.inbox`, `olivia.trigger`,
   `olivia.decide`, `olivia.strategy`, `olivia.observe`, `olivia.learn`,
   `olivia.home`, plus `olivia.cli`, which is the `olivia` command. Nothing in
   `edgar.*` imports `olivia.*`; `tests/unit/test_architecture.py` gains that
   rule. The distribution is `olivia-agent` with console scripts `olivia` and
   `olivia-agent` (so `uvx olivia-agent` works, as `edgar-harness` does).
   Olivia shares edgar's `.edgar/` and `~/.edgar/` for everything edgar
   already owns there: config, skills, agents, sessions, trust, grants, the
   receipt key. `.edgar` is a literal in 54 places across 30 files; making it
   injectable would be the largest seam on the line and a conflict on every
   merge. Only what is Olivia's own goes in `.olivia/`: its config sections
   (`[governor]`, `[inbox]`, `[otel]`, `[home]`, in `.olivia/config.toml`,
   since edgar's loader refuses unknown sections), `triggers.toml`, the
   inbox, the decision log, steer spools and home state.

2. **The governor answers after the engine, and cannot override a Deny.**
   Effective authority for one call is `engine ∧ ticket ∧ governor`, where the
   governor's answer replaces the engine's Ask and can veto its Allow:

   | Engine | Governor consulted | Result |
   |---|---|---|
   | Deny (hard layer, mode, rule) | no; the denial is recorded | Deny |
   | Ask | yes | the governor's allow or deny |
   | Allow | yes | the governor's allow or deny |
   | any, governor unreachable, slow or malformed | n/a | Deny, kind `governor_unavailable` |

   A governor allow is `Allow("governor")`, never a grant: nothing it says
   is written to the grants table, so a human's "always" and a policy's
   "yes" never mix. **Control-file writes are denied under the governor
   without asking it.** An unattended run that edits its own `AGENTS.md`,
   skills or policy is the loop OQ-2 closed. A person widens those by hand.
   Olivia's runs use mode `ask` with the governor attached; `yolo` and
   `auto` are refused when a governor is configured, because both allow
   without asking and the governor must see every call.

3. **Seams in edgar's non-removable code, and nothing else.**
   - `Guard.governor: Governor | None`, called as the table above says
     (about 10 lines of code, `permissions/guard.py`). A guard with a
     governor counts as interactive when it builds the `Policy`, so `decide()`
     returns Ask rather than turning it into a denial as it does for `-p`;
     `decide()` itself does not change.
   - `Session.steer(text, *, outside: bool = False)`. An outside steer is
     wrapped as untrusted data, taints the session and never becomes
     `PromptTyped`, so no intent, fact or synthesis reads it (about 6 lines of
     code, `core/session.py`).
   - `ErrorKind` gains `governor_denied` and `governor_unavailable` (2 lines
     of code, `core/message.py`).
   - The broker's ticket gains a sixth caveat, `subject` (use cases, point
     2). `edgar.broker` is removable, so this costs nothing against the
     9,500 limit, but it is still a change in `src/edgar/`.

   The first three are paid for by moving docstrings in non-removable files to `#`
   comments, which is free under ADR-0040 and changes no behaviour. 682 lines
   of code of docstrings remain outside the removable packages today. Each
   milestone that adds a seam frees its lines in the same commit, and
   `just loc` keeps "without removable packages" at ≤ 9,500. There is no
   seam for strategies: an alternative strategy is a runner in
   `olivia.strategy` that composes edgar's collaborators (context,
   providers, `execute`, verify) and emits edgar's events. `core/loop.py`
   stays the default strategy and is not touched. That is the whole of the
   "one loop" amendment (ADR-0067 item 4).

4. **Outside steers go through a spool.** A STEER decision appends to
   `.olivia/runs/<id>/steer.jsonl`. The running session's `olivia.trigger`
   watcher (an asyncio task, started only for runs Olivia launched) reads new
   lines and calls `session.steer(text, outside=True)`. The loop's one safe
   point is unchanged (ADR-0028).

5. **Budget.** 20,000 lines of code in total (ADR-0068 §12), counted by
   `tests/support/budget.py` over `src/edgar` and `src/olivia` together.
   edgar carries 12,191 today, which leaves 7,809 for Olivia. The milestone
   caps below add up to 5,300, leaving about 2,500 for what the milestones
   get wrong. A cap is a constraint: a milestone that does not fit moves
   work later and the number stays. Three limits hold on this line:
   `src/` ≤ 20,000; `src/edgar` without its removable packages ≤ 9,500;
   `core/loop.py` ≤ 200.

6. **Dependencies.** NFR-5's cap of 8 direct dependencies, counting extras,
   becomes 11 on this line. Olivia adds three, all in extras, none imported
   by `olivia.*` at startup and none by `edgar.*`: `cedarpy` and
   `cryptography` (Ed25519 signing) in `[governor]`, and
   `opentelemetry-sdk` in `[otel]`. Cedar is confined to the governor
   process (ADR-0068 §8). The agent side never evaluates policy. It stores
   the governor's signed answers, and verification runs in the governor's
   own command.

7. **Releases.** Olivia's `release.yml` runs only for tags matching
   `olivia-v*` and exits on any other. It publishes `olivia-agent` through
   its own PyPI trusted publisher and pushes `ghcr.io/vespassassina/olivia`.
   edgar's `release.yml` on `main` gains the mirror guard: it runs for `v*`
   tags only, so a release published from an Olivia tag can never publish
   `edgar-harness`. Olivia versions start at 0.1.0. 1.0 freezes the
   governor protocol, the inbox line format and the plugin entry points, as
   edgar 1.0 froze its extension formats.

8. **Milestones.** O-numbered, so they cannot collide with an M23 that edgar
   may add on `main`. The order follows ADR-0068 §13: nothing that runs
   without a person watching lands before the thing that would refuse it.

   | Milestone | What it proves | Cap (lines of code) | Release |
   |---|---|---|---|
   | O0 Fork skeleton | `olivia` installs, runs edgar unchanged, releases on its own tags | 150 | |
   | O1 Governor, fail closed | Every tool call answers to a Cedar policy through one protocol; a dead governor denies | 1,500 | |
   | O2 Inbox and trigger | Documents land, are decided on, and become governed runs; the first workload works end to end | 1,000 | 0.1.0 |
   | O3 Deciders and strategies | Jev-shaped deciders in two slots with fixed-rule fallback; a second runner beside the loop | 900 | 0.2.0 |
   | O4 Observability | Every decider, strategy and governor call is an event; OTel export | 350 | |
   | O5 Memory and learning ports | Server-backed memory as plugins; a pluggable learner bounded by policy | 500 | 0.3.0 |
   | O6 Home | Home Assistant events in, disabled automations out, routines and presence learned, actuators denied | 900 | |
   | O7 Olivia 1.0 | Formats frozen, tours, doctor, docs | 0, nothing new | 1.0.0 |

   The PRD is [`docs/olivia/PRD.md`](../olivia/PRD.md); the plan, broken
   down to files, requirement IDs and tests, is
   [`docs/olivia/ROADMAP.md`](../olivia/ROADMAP.md).

## Consequences

- **Load-bearing: the governor sees every call.** Mode `ask` plus the
  post-engine slot is what makes that true. A change that lets an Olivia run
  use `auto` or `yolo` with a governor attached, or that lets an engine Allow
  skip the slot, breaks ADR-0067 item 3.
- **Load-bearing: the governor cannot turn a Deny into an Allow.** The hard
  layer (credentials, control files, the receipt key, the policy files
  themselves) holds whatever the policy says.
- **Load-bearing: `edgar.*` never imports `olivia.*`.** It is what keeps
  merges from `main` cheap, and it is tested.
- **Unpleasant: two top-level packages in one distribution.** `olivia-agent`
  and `edgar-harness` cannot share an environment. `olivia doctor` says so if
  it finds both.
- **Unpleasant: Olivia's authority now depends on a second process.** A
  governor that is down stops all work, by design. The local adapter's
  install instructions include running it as a service under its own user,
  and `olivia doctor` reports whether the governor is sealed (another user,
  and the socket or pipe not writable by the agent's user) or only
  separate (same user, for development).
- **Windows is not exempt** (NFR-6). The local governor listens on a named
  pipe there and a Unix socket elsewhere. Running it as another user is a
  documented service install on all three platforms.
- The four seams in item 3 are the only Olivia changes to `src/edgar/`. A
  merge from `main` that conflicts anywhere else in `src/edgar/` means the
  rule was broken.
- CLAUDE.md says CI deletes the removable packages. It does not: the budget
  test and the import-graph test carry NFR-12. Olivia's CI adds a real job
  that deletes `src/olivia/` and runs edgar's suite, since that is cheap and
  proves the one-way rule outright.

## Rejected alternatives

- **A, rename the package.** Revisit when merges from `main` stop, which is
  also when ADR-0067's option B, a separate repository, comes back.
- **C, governor as asker plus veto.** Revisit if the post-engine slot ever
  has to change `decide()` itself. It does not today, because it runs after
  `decide()` and takes its result as input.
- **A new permission mode `governed`.** It would put a mode in `MODES` that
  only Olivia uses, and `decide()` would have to know about it. Mode `ask`
  plus the slot says the same thing with no change to the pure function.
- **Letting the governor answer control-file Asks.** Revisit if a regulated
  user needs an unattended run to update its own instructions under an
  audited policy. The answer then is a separate, human-countersigned change
  flow, not a policy rule.
- **Agent-side policy evaluation for speed.** It would put Cedar and the
  policy inside the process the policy constrains. Revisit only with a
  measured latency problem, and then as a cache of signed decisions, never
  as local evaluation.
