# Olivia — Product Requirements Document

| | |
|---|---|
| **Status** | Draft v0.1 · 2026-09-24 · the spec step of ADR-0067's design, spec, plan, test order |
| **Owner** | Diego |
| **Command** | `olivia` |
| **Package** | `olivia-agent` (PyPI), Python packages `olivia` and `edgar` |
| **Line** | the `olivia` branch; `main` merges in, never the reverse ([ADR-0067](../adr/0067-v5-fork-governable-autonomy.md)) |
| **Design** | [ADR-0067](../adr/0067-v5-fork-governable-autonomy.md) · [ADR-0068](../adr/0068-olivia-design-answers.md) · [ADR-0069](../adr/0069-olivia-tiers-and-milestones.md) · [use cases](use-cases.md) · [plan](ROADMAP.md) |

edgar's [PRD](../PRD.md) still holds on this line wherever this one is
silent. This document lists what Olivia adds and what it amends. It never
restates an edgar requirement to change it quietly; an amendment says
**Amends** and names the ID.

---

## 1. What this is

> **Olivia — the autonomous agent you can govern.**
> No human at run time. Every action answers to a policy a person wrote.
> A dead governor stops the work instead of waving it through.

Olivia is edgar 4.x plus what an unattended agent needs to be trusted with
real work: an external governor that decides every tool call against a Cedar
policy, an inbox that turns outside events into runs, a trigger strategy
that decides what each input becomes, pluggable deciders, strategies, memory
and learning, and a signed record a third party can check.

It keeps edgar's code readable. `src/edgar/` is edgar, changed only at the
four seams ADR-0069 lists. Olivia's own code sits in removable packages
under `src/olivia/`, capped with edgar at 20,000 lines of code.

## 2. Why it exists

edgar 4.0 runs unattended under a signed scope, but three things stop it
from doing a business's work alone:

1. **Authority ends where the human does.** An Ask with nobody to answer it
   is a denial, so an unattended edgar run can do only what `schedules.toml`
   pre-allowed. It cannot follow a policy that says "draft bills for
   invoices under €5,000 from known vendors".
2. **Nothing brings work in.** A schedule fires on a clock. It does not fire
   when an invoice arrives.
3. **The record is only as good as the machine it sits on.** ADR-0039's HMAC
   receipt is tamper-evident only against someone without the user's key.
   An auditor needs signatures from a process the agent cannot impersonate.

## 3. Who it is for

**Amends edgar PRD §3.** On this line:

**Primary: the operator of a regulated or cautious team.** Wants an agent
to process documents, tickets or HR events alone, and has to answer "on
whose authority did it do that?" to an auditor. Writes the policy, reads the
record, never watches the run.

**Secondary: the household running Home Assistant.** Wants the house to
handle what needs judgement (a leak while nobody is home, an appliance that
failed) and learn its routines, without any agent run touching a lock.

**Still not for:** multi-user or RBAC inside the agent (the governor is
where an organisation's identity lives), anyone who wants a GUI, and
real-time voice or chat (no listener, ADR-0068 §2).

## 4. Principles

edgar's principles hold (edgar PRD §4), with ADR-0067's amendments. Five
rules carry Olivia; each has an acceptance test.

1. **Fail closed.** A governor that is unreachable, slow, malformed or
   unsigned denies. There is no "allow on timeout" setting.
2. **Policy written by a human widens; nothing else does.** No model,
   decider, strategy, learner, plugin or input widens authority. The
   governor answers from policy, and an answer is never stored as a grant.
3. **An input is data, never authority.** Inbox text never becomes an
   intent. A run started from an input gets its authority from the policy.
4. **Nothing on the authorisation path is a model.** Deciders advise
   routing, triggers and learning; they never feed `decide()`, a ticket or
   the governor.
5. **Everything is an event.** Every decider call, strategy step, trigger
   decision, governor request and learner write is on the bus and in the
   record. A governor can only rule on what it can see.

## 5. Scope

### 5.1 Scope by milestone

| Area | IDs | Milestone |
|---|---|---|
| The fork itself | OLV-1..7 | O0 |
| Governor protocol, adapters, fail closed | GOV-1..16 | O1 |
| Inbox | INB-1..6 | O2 |
| Trigger strategy | TRG-1..10 | O2 |
| Deciders | DEC-1..6 | O3 |
| Strategies | STR-1..5 | O3 |
| Observability | OBS-1..5 | O4 |
| Memory plugins | MEM-O1..3 | O5 |
| Learning strategy | LRN-1..6 | O5 |
| Home | HOME-1..11 | O6 |
| Non-functional | ONFR-1..8 | from O0 |

### 5.2 Non-goals on this line

edgar's Never list holds except where ADR-0067 and ADR-0068 amend it:
a governor process or service is allowed (ADR-0067 item 4); user modelling
is allowed for home routines, including presence (ADR-0068 §4). Still never,
here too:

- **A listener in the agent.** Inputs arrive through the inbox; webhook
  relays live outside Olivia and write inbox files.
- **A human prompt during a governed run.** Hand-off is an action, a draft a
  person approves in the system of record, never a question the run waits on.
- **Policy evaluation inside the agent process.** Cedar runs in the governor.
- **Automatic enabling of a written automation.** Olivia writes it disabled.
  A person switches it on.
- **A marketplace for deciders, strategies or learners.** Plugins are
  installed packages the operator chose, as edgar's providers are.

### 5.3 Deferred

A listener for voice and live chat (use cases §3), a terminal live view and
a receipts-only sink (ADR-0068 §10), vendor APIs Home Assistant cannot reach,
multi-household or multi-tenant governors.

## 6. User journeys

Each journey is an acceptance test on the fake provider and a fake governor
speaking the real protocol, plus one run against the local Cedar governor.

### OJ1 — An invoice becomes a draft bill (O2)

A relay drops `acme-2026-0917.pdf`'s extracted text into the inbox as one
JSONL line with `source = "mail:ap@"` and `kind = "document"`. At the next
tick the trigger strategy buffers it with the other Acme documents that
arrived that day, then queues one run per document. The run reads the
purchasing system through an HTTP tool, extracts fields, matches the PO with
a pure check, and calls `create_draft_bill`. The governor allows the draft,
because the policy permits drafts for known vendors under €5,000. It denies
`post_bill` because nothing permits it. The verify step checks totals.
`olivia receipt` shows the input, the trigger decision, each governor
request with its signed answer, and the draft's id.

### OJ2 — The governor dies mid-run (O1)

A run is three tool calls in when the governor process is killed. The
fourth call is denied with `governor_unavailable` within the timeout. The
model sees the error, the run ends without further tool calls, the run's
exit code says a governor denial ended it, and the receipt shows no allow
after the last signed answer. Restarting the governor and re-draining the
inbox retries the input; nothing ran twice.

### OJ3 — A follow-up steers a running session (O2)

A customer's second mail arrives while the first mail's run is still going.
The trigger strategy decides STEER. The text lands at the next safe point as
outside data, the session is tainted, no intent or fact is created from it,
and the governor sees the tainted flag on every request after it.

### OJ4 — A leak while nobody is home (O6)

Home Assistant writes a `water_leak` event to the inbox. Presence, learned
from device events, says the house is empty. The trigger strategy decides
RUN_NOW, because a human-written rule grants it to leak events. The run
closes the smart valve (allowed), notifies the household (allowed) and tries
to unlock the front door for a plumber (denied: locks are denied by default,
whatever the routine learner proposes). The record shows all three.

### OJ5 — An organisation swaps the governor (O1)

An operator points `[governor] adapter = "remote"` at their own service
speaking the protocol. No Olivia code changes. `olivia governor test` sends
the protocol's conformance requests and reports which the service answers
correctly.

## 7. Functional requirements

### 7.1 The fork (O0)

| ID | Requirement | Priority |
|---|---|---|
| OLV-1 | Distribution `olivia-agent`; console scripts `olivia` and `olivia-agent`; `olivia --version` prints Olivia's version and the edgar version it carries | Must |
| OLV-2 | `olivia` with no Olivia subcommand behaves as `edgar`, on the same `.edgar/` state. Olivia's own config and state live in `.olivia/` and `~/.olivia/` (ADR-0069 item 1); nothing under `.edgar/` names Olivia | Must |
| OLV-3 | Nothing in `edgar.*` imports `olivia.*`: an import-graph test, and a CI job that deletes `src/olivia/` and runs edgar's suite green | Must |
| OLV-4 | Olivia's release workflow runs only for `olivia-v*` tags and publishes `olivia-agent` and `ghcr.io/vespassassina/olivia`; edgar's runs only for `v*` tags | Must |
| OLV-5 | `tests/support/budget.py` on this line counts `src/edgar` and `src/olivia` together against 20,000, keeps `src/edgar` without removable packages ≤ 9,500 and `core/loop.py` ≤ 200 | Must |
| OLV-6 | `olivia doctor` extends `edgar doctor` with: governor reachable, sealed or only separate, policy loaded, key fingerprints, inbox writable, `edgar-harness` in the same environment | Must |
| OLV-7 | Olivia's packages are removable one by one, from the leaves inward: deleting `olivia.home`, then `olivia.learn`, `olivia.observe`, `olivia.strategy`, `olivia.decide` leaves the rest green. `olivia.governor` is never removable once O1 ships, because an Olivia without it must refuse to run unattended (GOV-12) | Should |

### 7.2 The governor (O1)

| ID | Requirement | Priority |
|---|---|---|
| GOV-1 | **One protocol.** A request carries `request_id`, `intent_id`, `actor` (`inbox:SOURCE`, `schedule:NAME`, `task:NAME#n`), `action` (tool name), `resource` (the resolved subject: paths, host, argv), `subject` (whom the action is for, when known), `context` (mode, tainted, engine decision and reason, input id, calls so far). A response carries `request_id`, `decision` (`allow`, `deny`), `reason`, `policy_ids`, `issued_at` and an Ed25519 `signature` over the canonical JSON of request and response | Must |
| GOV-2 | The protocol is newline-delimited JSON, versioned by a `protocol` field. Local transport: a Unix socket, or a named pipe on Windows. Remote transport: HTTPS POST with the same bodies | Must |
| GOV-3 | `Guard.governor` is consulted after `decide()` for every Allow and Ask; an engine Deny is recorded and never sent (ADR-0069 item 2) | Must |
| GOV-4 | **Fail closed.** No answer within `[governor] timeout` (default 2 s, maximum 30 s), a connection error, a malformed body, a mismatched `request_id` or a bad signature is `Deny` with `ErrorRecord` kind `governor_unavailable`. No setting turns this into an allow | Must |
| GOV-5 | A governor deny is a `ToolResultBlock(is_error=True)` with kind `governor_denied`, naming the policy ids, and returns to the model (edgar invariant 4) | Must |
| GOV-6 | A governor allow is `Allow("governor")` and is never written to grants | Must |
| GOV-7 | Control-file writes and edits are denied under a governor without a request (ADR-0069 item 2) | Must |
| GOV-8 | With a governor configured, modes `auto` and `yolo` are refused at startup with an error naming the mode | Must |
| GOV-9 | **Subject caveat.** The broker's ticket gains a sixth caveat, `subject`, the ids an action may be for; a request naming another subject is refused before the governor is asked. Pure, property-tested with the other five (CAP-9) | Must |
| GOV-10 | **The local governor**, `olivia-governor` (`[governor]` extra), is a separate process holding the Cedar policy set and the signing key. It loads policy at start and on `SIGHUP`; a policy that fails Cedar validation against Olivia's schema is refused and the previous one stays | Must |
| GOV-11 | Olivia's Cedar schema names entity types `Actor`, `Action`, `Resource`, `Subject` and the context attributes of GOV-1, and ships with a default policy that permits nothing | Must |
| GOV-12 | `olivia run`, the inbox and `schedule tick` under Olivia refuse to start an unattended run when no governor is configured. `olivia` interactive sessions without one behave as edgar does | Must |
| GOV-13 | Every request and signed response is appended to the run's receipt beside edgar's broker lines. `olivia receipt --verify` checks edgar's HMAC chain and every governor signature against the governor's public key | Must |
| GOV-14 | `olivia governor test [--remote URL]` runs the protocol conformance set: allow, deny, timeout, malformed, wrong id, bad signature, unknown protocol version | Must |
| GOV-15 | `olivia policy check FILE` validates a policy against the schema; `olivia policy explain REQUEST.json` prints which policies decided a recorded request | Must |
| GOV-16 | `olivia policy prove FILE --never ACTION` uses Cedar's analysis to show a policy never permits an action (ADR-0068 §8's reason for Cedar) | Should |

### 7.3 Inbox (O2)

| ID | Requirement | Priority |
|---|---|---|
| INB-1 | The inbox is `.olivia/inbox/`. A producer writes a file ending `.jsonl` atomically (write to `.tmp`, then rename); one line per input: `id`, `source`, `kind`, `received_at`, `text`, optional `attachments` (paths inside `.olivia/inbox/files/`), optional `subject` | Must |
| INB-2 | `schedule tick` under Olivia drains the inbox before running due schedules: each line is decided on once, then the file moves to `.olivia/inbox/done/` | Must |
| INB-3 | Drain is exactly-once per input id: a crash mid-drain re-reads the file and skips ids already decided, using the decision log (TRG-7) | Must |
| INB-4 | A malformed line is refused with reason `malformed`, recorded, and does not stop the rest of the file | Must |
| INB-5 | Input text reaches a run only as untrusted data: never `PromptTyped`, never an intent, never an active fact (principle 3) | Must |
| INB-6 | `olivia inbox list|show ID|requeue ID`; `requeue` is a human action and records its actor | Should |

### 7.4 Trigger strategy (O2)

| ID | Requirement | Priority |
|---|---|---|
| TRG-1 | Each input gets exactly one of five outcomes: BUFFER, QUEUE, STEER, REFUSE, RUN_NOW (ADR-0068 §3) | Must |
| TRG-2 | The default strategy is fixed rules in `.olivia/triggers.toml`, matched in order on `source`, `kind` and optional fields; no match is REFUSE with reason `no_rule` | Must |
| TRG-3 | BUFFER holds the input under a key (for example vendor and day) with a release condition (`count`, `quiet_for`, `until`); on release the buffered inputs become one QUEUE decision carrying all their ids | Must |
| TRG-4 | QUEUE starts a run at the next tick with the rule's prompt template, agent, model and scope; the input's text is attached as untrusted data | Must |
| TRG-5 | STEER needs a running session for the rule's key; it appends to that run's `steer.jsonl` and lands as `session.steer(text, outside=True)`. No running session: the rule's fallback outcome, QUEUE by default | Must |
| TRG-6 | RUN_NOW starts in the tick that drained it, ahead of queued runs, using one slot past `[inbox] max_concurrent`. It is valid only in a rule that also sets `run_now = true`; the default policy grants it to nothing, and the governor sees `trigger = "run_now"` in context | Must |
| TRG-7 | Every decision is an event (`TriggerDecided`) and a line in `.olivia/decisions.jsonl` with input id, outcome, rule, decider and confidence if one was used | Must |
| TRG-8 | A decider (DEC-1) may choose among the outcomes a rule allows, never outside them; below its threshold, the rule's fixed outcome applies | Must |
| TRG-9 | `[inbox] max_concurrent` (default 1) and `max_per_hour` (default 60) cap runs; over a cap, QUEUE waits and RUN_NOW is refused with reason `cap` | Must |
| TRG-10 | The first workload ships as an example: `examples/olivia/documents/` with a triggers file, an agent, HTTP tools for a fake purchasing API, a Cedar policy and a verify check, 0 lines of `src/` | Must |

### 7.5 Deciders (O3)

| ID | Requirement | Priority |
|---|---|---|
| DEC-1 | Two protocols, `TriggerDecider.decide(input, allowed) -> Choice` and `StrategyDecider.decide(task, options) -> Choice`, where `Choice` is `label` and `confidence` in [0, 1] | Must |
| DEC-2 | Each registers through its own entry-point group, `olivia.trigger_deciders` and `olivia.strategy_deciders`; enabling one never enables the other (ADR-0068 §6) | Must |
| DEC-3 | Each slot has a `threshold` (default 0.8); below it, or on any exception or timeout, the fixed rule decides and `DeciderFellBack` is emitted | Must |
| DEC-4 | A decider receives the input's `source`, `kind` and text and nothing else: no policy, no ticket, no governor answer. Nothing it returns reaches `decide()`, a ticket or the governor (principle 4) | Must |
| DEC-5 | A decider's host is a governor-checked resource: its network call is a request with action `decider:NAME` before it is made | Must |
| DEC-6 | An example Jev adapter in `examples/olivia/jev-decider/` as a package with a cassette, 0 lines of `src/` | Should |

### 7.6 Strategies (O3)

| ID | Requirement | Priority |
|---|---|---|
| STR-1 | A `Strategy` protocol runs one task to completion with edgar's collaborators (context, provider, `execute`, verify) and edgar's events; `loop` (edgar's `core/loop.py`) is the default and is not changed (ADR-0069 item 3) | Must |
| STR-2 | Built-in strategies besides `loop`: `plan-execute` (one planning call, then steps, each step a loop turn) and `cheap-first` (the task on a routing tag's cheap model, escalating on a failed verify through edgar's escalation chain) | Should |
| STR-3 | A strategy is chosen per trigger rule or schedule entry, or by a StrategyDecider among the configured options | Must |
| STR-4 | Every strategy passes edgar's verify gate and pairing invariant; a property test runs each strategy against scripted providers and checks both | Must |
| STR-5 | Third-party strategies register through `olivia.strategies` entry points | Should |

### 7.7 Observability (O4)

| ID | Requirement | Priority |
|---|---|---|
| OBS-1 | New events: `InputReceived`, `TriggerDecided`, `DeciderCalled`, `DeciderFellBack`, `StrategyStep`, `GovernorRequested`, `GovernorAnswered`, `LearnerWrote`, `AutomationWritten` | Must |
| OBS-2 | `--events` carries them in the same JSONL shape as edgar's events | Must |
| OBS-3 | A completeness test: for each decider, strategy, trigger and learner call site, a scripted run shows its event; a call with no event fails the test | Must |
| OBS-4 | An OpenTelemetry exporter (`[otel]` extra) maps a run to a trace, a turn to a span and each event to a span event; the endpoint is only what the user configured (edgar PRV-15) | Must |
| OBS-5 | Input text, tool output and presence data are never exported to OTel unless `[otel] include_content = true` | Must |

### 7.8 Memory plugins (O5)

| ID | Requirement | Priority |
|---|---|---|
| MEM-O1 | SQLite FTS5 stays the default; server-backed stores register as edgar `Retriever` adapters (`edgar.retrievers`) | Must |
| MEM-O2 | Before a server-backed adapter connects, Olivia sends a governor request with action `memory:connect` and the host as resource; a deny disables the adapter for the session and falls back to FTS5 | Must |
| MEM-O3 | An example Redis or pgvector retriever in `examples/olivia/`, 0 lines of `src/` | Should |

### 7.9 Learning strategy (O5)

**Amends** edgar MEM-8, MEM-9 and SKL-8..16's reading limits on this line
(ADR-0068 §9). The boundary moves from what functions accept to policy.

| ID | Requirement | Priority |
|---|---|---|
| LRN-1 | A `Learner` protocol declares `sources` and `destinations` as data; every read from a source and write to a destination is a governor request (`learn:read`, `learn:write`) | Must |
| LRN-2 | The default learner is edgar's (ADR-0017), declaring edgar's sources and destinations only | Must |
| LRN-3 | The default policy denies `learn:read` on tool output, fetched content, inbox text and attachments; an operator widens by writing a policy (use cases, point 4) | Must |
| LRN-4 | A learned item records its sources; `olivia learned list|show|forget` shows and deletes it, and `forget` removes it from every destination | Must |
| LRN-5 | `auto` synthesis still needs a passing verify and writes only into machine-owned locations (edgar invariant 5) | Must |
| LRN-6 | Third-party learners register through `olivia.learners` entry points | Should |

### 7.10 Home (O6)

**Amends** the Never list's "user modelling" for home routines on this line
(ADR-0068 §4).

| ID | Requirement | Priority |
|---|---|---|
| HOME-1 | Home Assistant is the one hub, reached through its MCP server integration; Olivia ships no vendor API code | Must |
| HOME-2 | An example HA automation writes events to Olivia's inbox with `source = "ha"` and `kind` the event type | Must |
| HOME-3 | **Denied actuators.** The shipped home policy forbids, by Cedar `forbid`, every service on locks, garage doors and covers marked as doors, alarm panels, cameras, ovens and hobs, and climate set-points outside a configured range. A `forbid` beats any `permit`, so a learned routine cannot unlock them | Must |
| HOME-4 | The agent writes automations and scripts only into `packages/olivia/` in the HA config, each created with `initial_state: false`; it never edits other HA files | Must |
| HOME-5 | An automation that names a denied entity is not written; the attempt is recorded | Must |
| HOME-6 | The routine learner reads device events (state changes from the inbox) and writes routines to `.olivia/home/routines.jsonl`: trigger pattern, action, support count, first and last seen | Must |
| HOME-7 | Presence (who is home, when) is derived from device-tracker events, stored in `.olivia/home/presence.db`, never sent to a model whose provider is not local unless `[home] presence_to_cloud = true` | Must |
| HOME-8 | A learned routine may be applied automatically (ADR-0068 §4) only through the governor, as action `home:apply_routine` with the routine as resource | Must |
| HOME-9 | `olivia home routines|presence|forget [--all]`: the household sees and deletes what was learned | Must |
| HOME-10 | Quiet hours and private rooms from `.olivia/home.toml` are context attributes on every home request | Must |
| HOME-11 | `olivia doctor` warns when the home learner is on and the governor is only separate, not sealed | Must |

## 8. Non-functional requirements

| ID | Requirement | Measure |
|---|---|---|
| ONFR-1 | **Size.** `src/` total; `src/edgar` without removable packages; `core/loop.py` (ADR-0069 item 5) | ≤ 20,000 · ≤ 9,500 · ≤ 200 lines of code |
| ONFR-2 | **Governor latency.** Local adapter round trip, allow path, with a 50-policy set | p95 ≤ 20 ms on a 2020-era laptop |
| ONFR-3 | **Startup.** `import olivia.cli.main` pulls in nothing edgar's NFR-1 bans, and no `cedarpy`, `cryptography` or `opentelemetry` | edgar's ≤ 150 ms budget, same `-X importtime` test |
| ONFR-4 | **Dependencies**, counting extras (ADR-0069 item 6) | ≤ 11 direct |
| ONFR-5 | **Platform parity.** The governor, inbox and trigger tests pass on Windows, macOS and Linux | Green matrix, no platform skips in `olivia.governor` |
| ONFR-6 | **Offline suite** for both packages | ≤ 90 s on CI |
| ONFR-7 | **Fail-closed coverage.** Every GOV-4 failure mode has a test that asserts Deny | 100% of the list |
| ONFR-8 | **Merge health.** A merge from `main` touches `src/edgar/` only where `main` changed it or at ADR-0069's seams | Checked by a script run after each merge |

## 9. Interface contracts

### 9.1 Command surface

```
olivia                         edgar's REPL, with Olivia's commands added
olivia -p TEXT                 one turn, as edgar -p
olivia run --input FILE        one governed run from one inbox line (testing)
olivia inbox list|show|requeue
olivia governor start|test|status
olivia policy check|explain|prove
olivia receipt [ID] [--refused] [--verify]
olivia learned list|show|forget
olivia home routines|presence|forget
olivia doctor
olivia schedule …              edgar's schedule commands; tick drains the inbox first
```

### 9.2 Exit codes

edgar's codes hold (edgar PRD §9.3). New: **10**, a governed run ended
because the governor denied or was unavailable on the call the run could
not continue without; **11**, a governed run was refused at start (no
governor, `auto` or `yolo` with a governor, policy failed validation).

### 9.3 On-disk layout

edgar's layout (edgar PRD §9.5) is unchanged: config, sessions with their
transcripts and `receipt.jsonl`, scheduled runs, trust and grants stay under
`.edgar/`. Olivia adds:

```
.olivia/
  config.toml           [governor], [inbox], [otel], [home] only
  triggers.toml         hand-authored
  inbox/                producers write here; done/ and files/ inside
  decisions.jsonl       machine-written, append-only
  runs/<id>/            steer.jsonl, keyed by edgar's session or run id
  home/                 routines.jsonl, presence.db (machine-written)
~/.olivia/
  governor/             the local governor's policy set, schema and key; owned by the governor's user
```

Machine-writable on this line, besides edgar's: `decisions.jsonl`, `runs/`, `home/`,
`inbox/done/`, and HA's `packages/olivia/`. Everything else is
hand-authored, as edgar PRD §9.5.

## 10. Risks

| Risk | Mitigation |
|---|---|
| The governor becomes a single point of failure and operators turn it off | GOV-12: no governor, no unattended run. There is nothing to turn off to get an allow |
| A policy is too broad and the agent does real damage within it | Draft-then-hand-off as the documented pattern; `policy prove --never`; the shipped defaults permit nothing |
| Presence data leaks through a cloud prompt | HOME-7's local-only default; OBS-5; `doctor` warnings |
| A learned routine acts ahead of people on something physical | HOME-3's `forbid` set, which no `permit` can beat; HOME-8 through the governor |
| Merges from `main` start to hurt | ONFR-8, and ADR-0067's revisit condition for a separate repository |
| Cedar's Python bindings lag the Rust core or break on a platform | Confined to the governor extra; the protocol lets a remote governor in any language replace it |

## 11. Success criteria

**0.1.0 ships when:** O0–O2 are done; OJ1, OJ2, OJ3 and OJ5 pass on three
platforms; every GOV-4 failure mode denies; the documents example runs
against the local Cedar governor end to end; `src/` ≤ 20,000 and the two
other limits of ONFR-1 hold.

**0.2.0 ships when:** O3 and O4 are done, OBS-3's completeness test passes,
and a StrategyDecider below threshold always takes the fixed rule.

**0.3.0 ships when:** O5 is done and a learner that declares a source the
policy denies reads nothing from it, shown by a test with a spy source.

**1.0.0 ships when:** O6 and O7 are done, OJ4 passes, the protocol, inbox
format and entry-point groups are documented as frozen, and one outside
person has written a policy for the documents example from the docs alone.

## 12. Open questions

| ID | Question | Lean | Blocks |
|---|---|---|---|
| OOQ-1 | Does a governor answer carry an expiry, so repeated identical calls can reuse it? | No in 0.x: one call, one request. Revisit on ONFR-2 numbers | O1 |
| OOQ-2 | Is the GitHub name `olivia` free of clashes that matter (ADR-0068 §1)? | Check before 0.1.0; the PyPI name `olivia-agent` is free | 0.1.0 |
| OOQ-3 | What holds the local governor's signing key on a machine with no TPM or keychain service account? | A file owned by the governor's user, mode 0600; `doctor` reports it | O1 |
| OOQ-4 | Does STEER need an explicit session key in the input, or is the rule's key enough? | The rule's key, from input fields | O2 |
| OOQ-5 | How does the household consent to presence learning, and where is that recorded? | `olivia home enable` asks once, per person, and records it in `.olivia/home/consent.jsonl` | O6 |
