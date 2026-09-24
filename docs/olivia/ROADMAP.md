# Olivia roadmap

Eight milestones on the `olivia` line, from the fork's skeleton to 1.0
([ADR-0069](../adr/0069-olivia-tiers-and-milestones.md)). Requirement IDs
trace to [`PRD.md`](PRD.md). Each milestone ships something tested and
documented and ends with its tour stops. Its lines-of-code cap is a
constraint: a milestone that does not fit moves work later, and the cap
stays.

edgar's rules for writing code hold here (`AGENTS.md`, ADR-0040): pseudocode
comments, shallow functions, sensible defaults, the tour in the same commit.
A milestone that adds a seam in `src/edgar/` frees the same lines there, by
moving docstrings to comments, in the same commit.

## Status

| Milestone | Status | Cap | Release |
|---|---|---|---|
| O0 Fork skeleton | Not started | 150 | |
| O1 Governor, fail closed | Not started | 1,500 | |
| O2 Inbox and trigger | Not started | 1,000 | 0.1.0 |
| O3 Deciders and strategies | Not started | 900 | 0.2.0 |
| O4 Observability | Not started | 350 | |
| O5 Memory and learning ports | Not started | 500 | 0.3.0 |
| O6 Home | Not started | 900 | |
| O7 Olivia 1.0 | Not started | 0 | 1.0.0 |

Starting point: `src/` at 12,191 of 20,000, of which 9,497 of 9,500 is
outside edgar's removable packages. `AGENTS.md` on this line needs the
maintainer's own edit before O0's code (ADR-0067 item 6); the proposed diff
goes in the journal, not the file.

---

## O0 — Fork skeleton

**Goal:** `olivia` installs, runs edgar unchanged under its own config roots,
and releases on its own tags without touching edgar's.

- `pyproject.toml`: distribution `olivia-agent`, console scripts `olivia`
  and `olivia-agent`, both packages in the wheel, extras `[governor]` and
  `[otel]` declared empty for now [OLV-1]
- `src/olivia/__init__.py`, `src/olivia/cli/main.py`: parse Olivia's own
  subcommands, hand the rest to `edgar.cli.main` unchanged; `.olivia/`
  holds only Olivia's own config and state [OLV-2]
- `tests/unit/test_architecture.py`: `edgar.*` never imports `olivia.*`
  [OLV-3]
- `.github/workflows/ci.yml`: a job that deletes `src/olivia/` and runs
  edgar's suite [OLV-3]
- `.github/workflows/release.yml` on this line: `olivia-v*` only, the
  `olivia-agent` publisher, `ghcr.io/vespassassina/olivia`; the mirror guard
  (`v*` only) proposed for `main` as a one-line change there [OLV-4]
- `tests/support/budget.py`: tier `olivia` at 20,000 over both packages,
  the ≤ 9,500 and ≤ 200 limits kept [OLV-5]
- `olivia doctor`: edgar's report plus "edgar-harness in the same
  environment" [OLV-6]
- `CHANGELOG.md` gains an "Olivia, unreleased" section, kept apart from
  edgar's
- **Tour delivery:** `docs/tour/olivia.html` with the fork's first stop:
  what `src/olivia/` is and the one-way import rule

**Done when:** `uv run olivia --version` prints both versions; `olivia -p`
runs a fake-provider turn exactly as `edgar -p` does; the delete-olivia CI
job is green; a dry run of the release workflow on an `olivia-v0.0.1-rc1`
tag in a fork builds `olivia-agent` and would push nothing named `edgar`.

---

## O1 — Governor, fail closed

**Goal:** every tool call in a governed run answers to a Cedar policy through
one protocol, and a governor that is gone denies. Nothing unattended lands
before this.

- `olivia/governor/protocol.py`: `Request`, `Response`, canonical JSON,
  protocol version; pure, property-tested round trip [GOV-1, GOV-2]
- `olivia/governor/client.py`: local (Unix socket, named pipe) and remote
  (HTTPS) adapters behind one `Governor` callable; timeout, id check,
  signature check, every failure a Deny [GOV-2, GOV-4]
- Seam: `Guard.governor` in `edgar/permissions/guard.py`, consulted after
  `decide()` for Allow and Ask; control-file writes denied without asking
  [GOV-3, GOV-6, GOV-7]. Frees its lines in the same commit
- Seam: `ErrorKind` gains `governor_denied`, `governor_unavailable` [GOV-5]
- Startup refusals: no governor for an unattended run, `auto` or `yolo`
  with a governor [GOV-8, GOV-12]
- `subject` caveat in `edgar/broker/caveats.py` and `authorize.py`,
  property-tested with the other five [GOV-9]. The broker is removable, so
  this costs nothing against the 9,500 limit
- `olivia/governor/server/`: `olivia-governor`, Cedar via `cedarpy`, Ed25519
  via `cryptography`, `SIGHUP` reload, refusing invalid policy [GOV-10]
- `olivia/governor/schema.cedarschema` and `default.cedar`, which permits
  nothing [GOV-11]
- Receipt lines for requests and signed answers; `olivia receipt --verify`
  checks both chains [GOV-13]
- `olivia governor start|test|status`, the conformance set [GOV-14]
- `olivia policy check|explain` [GOV-15]; `prove --never` if Cedar's
  analysis is reachable from `cedarpy`, else deferred with a note [GOV-16]
- `olivia doctor`: reachable, sealed or only separate, key fingerprints
  [OLV-6]
- Tests: every GOV-4 mode denies (ONFR-7); OJ2 and OJ5 on a fake governor
  speaking the real protocol; one OJ2 run against the real local governor;
  the confused-deputy test from M17 rerun under a governor; ONFR-2 measured
- **Tour delivery:** `docs/tour/governor.html`: the protocol, the table in
  ADR-0069 item 2, fail closed, sealed versus separate

**Done when:** a scripted run whose governor is killed after three calls
gets `governor_unavailable` on the fourth within the timeout and exits 10;
no Allow in the receipt lacks a valid signature; `policy check` refuses a
policy naming an unknown attribute; the three size limits hold.

---

## O2 — Inbox and trigger · **0.1.0**

**Goal:** documents land, are decided on, and become governed runs. The
first workload, document processing, works end to end.

- `olivia/inbox/format.py`: the line format, pure parse, `malformed`
  refusals [INB-1, INB-4]
- `olivia/inbox/drain.py`: drain before due schedules, exactly-once by
  input id against `decisions.jsonl`, move to `done/` [INB-2, INB-3]
- `olivia/trigger/rules.py`: `triggers.toml` parser, ordered matching,
  `no_rule` refusal; pure [TRG-2]
- `olivia/trigger/outcomes.py`: BUFFER with key and release condition,
  QUEUE, STEER with fallback, REFUSE, RUN_NOW with its rule flag and the
  extra slot; caps [TRG-1, TRG-3..6, TRG-9]
- Seam: `Session.steer(text, *, outside=False)` in `edgar/core/session.py`;
  `olivia/trigger/steer.py` watches `runs/<id>/steer.jsonl` [TRG-5, INB-5]
- `TriggerDecided` and `decisions.jsonl` [TRG-7]
- `olivia run --input FILE`, `olivia inbox list|show|requeue` [INB-6]
- `examples/olivia/documents/`: triggers, agent, HTTP tools against a fake
  purchasing API in the test suite, a Cedar policy permitting drafts for
  known vendors under €5,000, a verify check on totals [TRG-10]
- Tests: OJ1 and OJ3 on three platforms; a crash between decide and move
  replays without a second run; input text never appears in `PromptTyped`,
  an intent or a fact (property test over random inputs)
- **Tour delivery:** `docs/tour/inbox.html`: from a file in `inbox/` to a
  governed run, stop by stop
- **Release:** 0.1.0 when PRD §11's 0.1.0 criteria hold; OOQ-2 checked
  first

**Done when:** PRD §11's 0.1.0 criteria hold.

---

## O3 — Deciders and strategies · **0.2.0**

**Goal:** System 1 choices in two separate slots, each falling back to a
fixed rule, and a second way to run a task beside edgar's loop.

- `olivia/decide/base.py`: `TriggerDecider`, `StrategyDecider`, `Choice`;
  entry-point groups; thresholds; fallback on low confidence, exception or
  timeout [DEC-1..3]
- A decider sees `source`, `kind` and text only; its host is a governor
  request `decider:NAME` [DEC-4, DEC-5]
- The trigger strategy calls the TriggerDecider within a rule's allowed
  outcomes [TRG-8]
- `olivia/strategy/base.py`: `Strategy`; `loop` wraps edgar's loop
  untouched [STR-1]
- `olivia/strategy/plan_execute.py`, `cheap_first.py` [STR-2]
- Strategy per trigger rule or schedule entry, or by StrategyDecider
  [STR-3]; `olivia.strategies` entry points [STR-5]
- `examples/olivia/jev-decider/` with a cassette [DEC-6]
- Tests: a property test over scripted providers holds the pairing invariant
  and the verify gate for every strategy [STR-4]; a decider returning a
  label outside `allowed` is ignored; a decider below threshold never
  changes an outcome
- **Tour delivery:** `docs/tour/deciders.html`: why a decider is not on the
  authorisation path, and where each slot sits
- **Release:** 0.2.0 with O4

**Done when:** a TriggerDecider at 0.79 confidence against a 0.8 threshold
leaves every outcome to the rule, in a test that would fail if it did not;
`plan-execute` passes the documents example.

---

## O4 — Observability

**Goal:** every call Olivia adds is visible, in the terminal and in an
organisation's own tracing.

- The OBS-1 events in `olivia/observe/events.py`, emitted at each call site
  [OBS-1]
- `--events` carries them [OBS-2]
- The completeness test [OBS-3]
- `olivia/observe/otel.py` in `[otel]`: run as trace, turn as span, events as
  span events; content off by default [OBS-4, OBS-5]
- **Tour delivery:** a stop in `governor.html` or its own page: from the bus
  to a span

**Done when:** OBS-3's test fails when any one emit is removed (checked by
removing one); an OTel export of OJ1 against an in-memory exporter holds no
input text with `include_content` off.

---

## O5 — Memory and learning ports · **0.3.0**

**Goal:** memory and learning become pluggable, and the policy, not the
code, bounds what a learner reads and writes.

- Server-backed memory as `edgar.retrievers` adapters; `memory:connect`
  governor request, FTS5 fallback on deny [MEM-O1, MEM-O2]
- `examples/olivia/redis-retriever/` [MEM-O3]
- `olivia/learn/base.py`: `Learner` with declared sources and destinations;
  a governor request per read and write [LRN-1]
- edgar's learner as the default, declaring its own sources only [LRN-2]
- The default policy's `forbid` on tool output, fetched content, inbox text
  and attachments [LRN-3]
- `olivia learned list|show|forget`, provenance per item [LRN-4]
- `auto` synthesis still gated on verify and `learned/` [LRN-5];
  `olivia.learners` entry points [LRN-6]
- Tests: a spy source a learner declares but the policy denies is never read
  (PRD §11, 0.3.0); `forget` removes an item from every destination
- **Tour delivery:** `docs/tour/learning-ports.html`: where the learning
  boundary moved and what now enforces it

**Done when:** PRD §11's 0.3.0 criteria hold.

---

## O6 — Home

**Goal:** Home Assistant events in, disabled automations out, routines and
presence learned, every physical actuator denied.

- HA through its MCP server, configured in `examples/olivia/home/`; an HA
  automation writing events to the inbox [HOME-1, HOME-2]
- `examples/olivia/home/home.cedar`: the `forbid` set for locks, doors,
  alarms, cameras, ovens, hobs and out-of-range set-points [HOME-3]
- `olivia/home/automations.py`: writes into `packages/olivia/` with
  `initial_state: false`, never elsewhere, never naming a denied entity
  [HOME-4, HOME-5]
- `olivia/home/routines.py`: the routine learner over device events
  [HOME-6]; applying one goes through the governor [HOME-8]
- `olivia/home/presence.py`: presence from device trackers, local only by
  default [HOME-7]
- `olivia home enable|routines|presence|forget`; consent recorded (OOQ-5)
  [HOME-9]
- Quiet hours and private rooms as context [HOME-10]; the `doctor` warning
  [HOME-11]
- Tests: OJ4; a learned routine to unlock the front door is refused by
  `forbid` even with a `permit` for it; presence never reaches a cloud
  provider's request body with the default config
- **Tour delivery:** `docs/tour/home.html`: reflexes in HA, judgement in
  Olivia, and why an automation is standing authority

**Done when:** OJ4 passes, and a policy that `permit`s everything still
cannot actuate one item on HOME-3's list.

---

## O7 — Olivia 1.0

**Goal:** freeze what others build against, and prove the docs are enough.

- The governor protocol, inbox line format and the four entry-point groups
  documented as frozen, as edgar's EXT-10
- Tours complete, the map current, `olivia doctor` complete
- An outside person writes a policy for the documents example from the docs
  alone (PRD §11)
- No new code: anything this milestone finds missing moves to 1.1

**Done when:** PRD §11's 1.0.0 criteria hold.
