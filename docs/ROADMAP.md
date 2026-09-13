# Roadmap

Seventeen milestones in three tiers ([ADR-0015](adr/0015-release-tiers.md)). Each
milestone ships something that works, is tested, and is documented. Nothing is
"done later". Each tier ends in a release.

| Tier | Milestones | Release | Promise | Source budget |
|---|---|---|---|---|
| **Core** | M0–M6 | 0.x | Read it in an afternoon, use it every day | ≤ 5,000 LOC |
| **v1** | M7–M11 | 1.0 | Extensible and remembers; extension formats frozen | ≤ 8,000 LOC |
| **v2** | M12–M16 | 2.0 | Learns and runs unattended; removable | ≤ 11,000 LOC |

## Status

Milestone IDs keep their numbers; the order of work is **M0, M1, M2, M4, M3, M5,
M6**, then v1 ([ADR-0033](adr/0033-replan-after-m2.md)). The day-by-day record is
[`JOURNAL.md`](JOURNAL.md); user-visible changes are in
[`CHANGELOG.md`](../CHANGELOG.md).

| Milestone | Status | Shipped in |
|---|---|---|
| M0 Skeleton | Done | 0.0.1, 0.0.2 |
| M1 The loop | Done | unreleased (`2c25162`) |
| M2 Real providers | Done | unreleased (`ff4db71`) |
| M4 REPL, streams, model picker | Done | unreleased |
| M3 Tools, permissions, verify, custom tools, trust | Done | unreleased |
| M5 Context and sessions | **Next**, after the budget decision (ADR-0036) | |
| M6 Skills, login, Core release | Planned | 0.1 |
| M7–M16 | Planned | 1.0, 2.0 |

Milestones reference PRD requirement IDs; PRD §5.1 maps every ID to its tier. A
milestone is complete when its IDs are implemented, its tests pass on all three
platforms, and its docs are written. If a milestone pushes its tier over budget,
something moves to a later tier; the budget does not move.

---

# Core — 0.x

## M0 — Skeleton

**Goal:** a package that installs and runs on three platforms, and a CI matrix that
proves it.

- `pyproject.toml`, `src/edgar/` layout, `uv` workflow
- `justfile`: `test`, `check`, `cov`, `fmt`
- CI matrix `{ubuntu, macos, windows} × {3.12, 3.13}`
- `ruff`, `mypy --strict`, `pytest` all wired and green on an empty suite
- `edgar --version` works
- AGPL-3.0 licence (ADR-0026), README stub, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY
- **[NFR-1] startup budget test in place before there is anything to regress**
- **[NFR-12] tier-isolation import test in place, trivially green**
- **[EXT-11] ports import test in place: core imports no adapter**
- **[NFR-4] LOC counter in CI, reporting against the Core budget**
- **[NFR-14] `SECURITY.md` with a monitored contact, hash-pinned lockfile, trusted
  publishing configured before the first release**

**Done when:** `uvx edgar-harness --version` works on all three OSes from a clean machine.

---

## M1 — The loop, with a fake provider and real config

**Goal:** a working turn loop with zero network, reading real config. This is the
milestone that makes everything else testable.

- `core/message.py` — canonical types, `ErrorRecord`, `attached` text [§3.1]
- `core/units.py` — unit grouping, strengthened pairing invariant, property-tested [CTX-4]
- `core/events.py` — event bus [ADR-0011]
- `core/loop.py` — the turn loop, sequential tool execution [TOOL-12]
- `core/session.py` — in-memory for now
- `providers/base.py` + `providers/fake.py` [ADR-0009 layer 1]
- `tools/base.py`, `tools/registry.py`, `tools/execute.py`, `tools/spill.py` [TOOL-1..4]
- Two built-ins: `read`, `ls`
- `prompts/system.md` and `context/prompts.py`; `edgar prompt show`; prompt budget
  test [CTX-16, NFR-13]
- `config/schema.py`, `config/load.py` — layering with provenance, hand-written
  validation, read once at session start [CFG-1..3, CFG-8]
- `cli/main.py` with `-p` only, plain stdout

**Done when:** `edgar -p "read a.txt" --model fake/test --mode read-only` executes
a tool and returns text, with the full event sequence assertable in a test, and a
bad config key produces an error naming the file, key and expected type.

**Deliberately first:** the fake provider before any real one. It is the leverage.
Config lands here, not at the end, because every later milestone reads it.

---

## M2 — Real providers

**Goal:** five providers behind two adapters, plus any OpenAI-compatible server,
all passing one contract suite.

- `providers/registry.py` with lazy loading and user-defined providers [PRV-4, PRV-12]
- `providers/openai_compat.py` + `providers/quirks.py` [PRV-1, PRV-3]
- `providers/anthropic.py` [PRV-2]
- Streaming normalisation: text, tool calls, reasoning with `origin` [PRV-5, PRV-13]
- `providers/repair.py` — deterministic tool-call repair; prompt profiles [PRV-16, PRV-17]
- No implicit models or hosts: auxiliary roles default to the main model [PRV-15]
- Retries with backoff, `Retry-After` [PRV-7]
- Usage and cost, approximate flagged [PRV-6, BUD-1]
- `providers/pricing.py` [BUD-5]
- `providers/routing.py` — pure `select_model()` with static roles only [ROUTE-1]
- **Contract suite** across all providers, including a user-defined one against a
  local fixture server [ADR-0009 layer 2]
- Cassette recording harness [layer 3]
- `edgar models list`

**Done when:** the contract suite passes identically for all five named providers
against cassettes offline, a `[providers.local]` block reaches a fixture server
with no code change, foreign reasoning blocks are dropped on serialisation, and a
local model that emits tool calls inside code fences completes the fake-task set
through repair.

**Resolves:** OQ-3 (tokenisation approach).

---

## M3 — Tools, permissions, the verify gate and custom tools

**Built after M4** ([ADR-0033](adr/0033-replan-after-m2.md)).

**Goal:** the safety boundary, exhaustively tested, and "done means verified";
and the agent gets CLIs and APIs without MCP or Python.

- `permissions/policy.py` — pure `decide()` with `tainted` and control paths [PERM-1..5, PERM-11, PERM-12]
- `permissions/matcher.py` — hostile paths, shell segments [PERM-5, PERM-14]
- `permissions/control.py` — control-file set and hashes [PERM-12]
- `permissions/grants.py` + `storage/db.py` (sessions index, grants, trust tables) [PERM-6]
- The audit trail: `PermissionResolved` with tool, subject, source and reason for
  every decision [PERM-10]; its file copy arrives with the M5 session record
- Non-interactive requires explicit `--mode`, exit 3 [CLI-9, PERM-7]
- `yolo` gated behind env var plus typed confirmation [PERM-9]
- Remaining built-ins: `write`, `edit`, `glob`, `grep`, `shell` (per-platform
  selection), `fetch` (untrusted, sets taint) [TOOL-5, TOOL-11, TOOL-13]
- `core/verify.py` — the verification gate, authorised before the turn [VER-1..7]
- `--verify`, `verify.command`, `verify.max_attempts`; exit 9 [CLI-17, VER-5]
- `edgar permissions list|revoke`
- `tools/custom.py` — command tools (argv templates) and HTTP tools (request
  templates, fixed host, `${env:…}` in headers only, redaction) [TOOL-6], moved
  from M6: a few dozen tokens each, where an MCP server costs thousands
- `cli/trust.py` — project trust, `edgar trust`, `--no-project-exec` [PERM-13,
  CLI-19], moved from M6 because project config can now declare a command tool
- `/browser`: moved to M8 with its MCP form; a browser CLI can already be declared
  as a command tool ([ADR-0036](adr/0036-safety-layer-as-built.md)) [CLI-29]
- Property tests: hostile paths, control files never auto-allowed outside `yolo`,
  tainted `auto` never allows shell by mode default, deny-any-segment; 100% branch
  coverage on the package

**Done when:** the permission matrix is exhaustively tested and no generated
hostile path escapes the root; with the fake provider a turn that fails its check
twice exits 9 with the event sequence `VerifyStarted` → `VerifyFinished(ok=False)`
→ `RequestStarted` → … asserted in a test; a `write` to `.edgar/config.toml`
in `auto` mode prompts; a command-tool argument containing `; rm -rf ~` reaches
the program as one argv element, an HTTP tool cannot be pointed at another host,
the token never appears in transcript, events or logs, and an untrusted
non-interactive run exits 3.

**Resolves:** OQ-7 (taint scope).

---

## M4 — The CLI: REPL, status line, streams, model picker

**Built next, before M3** ([ADR-0033](adr/0033-replan-after-m2.md)).

**Goal:** the daily driver, and a clean surface for programs.

- `cli/repl.py` — input, history, streaming [CLI-1]
- `cli/statusbar.py` — stderr, TTY-only, throttled, shows taint [CLI-5, CLI-6]
- `cli/render.py` — line-at-a-time output, `NO_COLOR`, stdout discipline [CLI-15];
  Markdown is left as written ([ADR-0035](adr/0035-repl-as-built.md))
- `cli/slash.py` — `/help /model /mode /compact /cost /quit` [CLI-14]
- One prompt queue: questions go through the REPL's own prompt (`Shell.ask`); the
  permission prompts that use it arrive with M3 [TOOL-12]
- Terminal-native output: no alternate screen, native scrollback [CLI-23]
- `--show-thinking`, `/thinking` [CLI-21]
- Ctrl-C once cancels, twice exits; cancelled calls get synthetic results [CLI-12]
- Input during a turn: plain text queues, `/queue`, `/steer` at the loop's safe
  point, `/btw` side questions via `core/aside.py` [CLI-13, CLI-24, ADR-0028]
- Turn control and status: `/stop`, `/pause`, `/resume`, `/status`, `/model` with
  mid-session switching [CLI-27, CLI-28, ADR-0029]
- `edgar models` and `/model` with no argument: an interactive picker that lists
  a provider's models on request and creates a config but never edits one
  [CLI-30, ADR-0034]
- `core/cancel.py` — cancellation scopes [TOOL-10]
- Windows VT enablement with plain-line fallback
- `--quiet`, `--json`, `--events` [CLI-7, CLI-8, CLI-18]

**Done when:** a real interactive session feels good on all three terminals;
`edgar -p "hi" > out.txt 2>/dev/null` yields a file with no ANSI bytes; Ctrl-C
during a tool call leaves a transcript that passes the invariant; `--events` output
parses line by line as JSON; a `/steer` sent at any moment of a turn lands between
units, and a `/btw` answer leaves the transcript unchanged.

---

## M5 — Context and sessions

**Goal:** long sessions that do not fall over, and that survive a restart.

- `context/builder.py` — assembly order with the cache breakpoint, byte-stable
  prefix and its test [CTX-1, CTX-15, CTX-17]
- `context/working.py`, `todo` tool, plan mode (`/plan`, `/go`, `--plan`)
  [CTX-18, TOOL-14, CLI-20]
- `context/tokens.py` — exact plus approximate [CTX-9]
- `context/pins.py` [CTX-5]
- `context/compact.py` — S1 elide, S2 summarise, S3 overflow, hysteresis [CTX-3, CTX-6, CTX-11, CTX-12]
- `edgar context show` with per-section token counts [CTX-2]
- `/compact` with optional focus [CTX-7]
- `storage/transcript.py` — JSONL with compaction records [CTX-14, ADR-0010]
- `--resume`, `--continue`, `edgar sessions list|show|rm` [CLI-11]
- Session commands as appended records: `/new /clear /reset /history /undo /retry
  /title /sessions /load /save`, `edgar --load` [CLI-25, CLI-26, CLI-28, ADR-0029]
- `personality.md`, user and project scope, in `edgar prompt show` [CTX-19, ADR-0030]
- The control-file hash stored at session end, and the warning when it changed
  (moved from M3) [PERM-12]
- Turn, session and daily cost caps [BUD-2, BUD-3], `/cost`, `edgar cost` [BUD-6]
- Idempotency, overflow and spill tests [CTX-8]

**Done when:** a 200-turn session with heavy tool use autocompacts repeatedly,
including inside a single long tool-calling turn, without ever producing a
transcript that fails the invariant; most compactions use S1 only; `--resume`
rebuilds the compacted view and the working state; the prefix stays byte-identical
across every request between compactions; and pinned content that alone exceeds
the window raises `ContextOverflow` with a hint; `/undo 2` followed by
`--resume` shows exactly the conversation the user saw, and a `/save` file opens
on another machine.

---

## M6 — Skills, login and the Core release · **Core release**

**Goal:** skills, a login that never touches a subscription, and a release people
can fork. (Custom tools and trust moved to M3, [ADR-0033](adr/0033-replan-after-m2.md).)

- `edgar login PROVIDER` / `edgar logout`: OAuth with PKCE for providers that
  issue API keys that way (OpenRouter first), key kept in the OS keyring
  [PRV-18, CFG-6, ADR-0032]
- `skills/discovery.py` (PyYAML, lazily) and `skills/loader.py` + `skill` tool [SKL-1..5]
- `edgar tools list|describe`, `edgar skills list|validate` [SKL-7]
- Collision order with startup warning (without MCP and extensions yet) [TOOL-9]
- Examples of each in `examples/`
- Short docs: README quick start, `docs/COOKBOOK.md` first recipes

**Done when:** J3 and J9 pass their acceptance tests end to end; `edgar login
openrouter` stores a key that `edgar -p` then uses, and a planted keyring value
never appears in transcript, events or logs; `src/` is under 5,000 LOC.

**Release:** 0.1 to PyPI. From here people can use and fork edgar.

---

# v1 — 1.0

## M7 — Memory and session search

**Goal:** the harness remembers what you tell it, and finds what it saw.

- `memory/store.py`, `facts.py` with pending and active states, FTS5 [MEM-3, MEM-6]
- Pinned set frozen at session start; capacity in the envelope header [MEM-6, MEM-7]
- `/remember TEXT`, `edgar memory add` [MEM-23]
- `remember` tool → pending, confirmed at turn end [MEM-21]; `recall` tool
- Session search over transcript text, `recall(scope="sessions")` [MEM-20]
- `memory/retriever.py` port with the `fts5` adapter (porter + trigram, multi-term
  `recall`) [MEM-24]
- Session forks: `/fork`, `--fork ID[@TURN]` [CLI-22]
- `memory/markdown.py` — round trip for `memory edit` [MEM-4]
- `memory/redact.py` [MEM-15]
- `edgar memory list|add|edit|review|forget|undo` [MEM-5]
- Contradiction detection for new facts [MEM-10], eviction [MEM-11]

**Done when:** a fact saved in session 1 changes behaviour in session 4 and is
editable and revertible; a declined proposal is never injected; a fact saved
mid-session does not change the prompt prefix until the next session.

---

## M8 — MCP

**Goal:** the ecosystem, lazily.

- `tools/mcp/` — stdio and Streamable HTTP, discovery, lazy spawn [TOOL-7, TOOL-8]
- Namespacing `mcp__server__tool`, collision order [TOOL-9]
- MCP results untrusted, annotations ignored by `decide()` [TOOL-13]
- Deferred tool schemas and `tool_search` [TOOL-15]
- Project MCP servers require trust [PERM-13]
- `edgar mcp list|test`
- `/browser`: the `[browser]` preset, a command tool or an MCP server spawned on
  demand [CLI-29, ADR-0029, ADR-0036]
- OAuth for remote servers: OAuth 2.1 with PKCE, tokens in the keyring [TOOL-7,
  ADR-0032], moved from v2

**Done when:** a stdio server and a Streamable HTTP server both work, startup time
is unchanged with five servers configured, an MCP result taints the session, and
forty configured MCP tools cost no more than the schema budget per request.

---

## M9 — Subagents, routing rules and fallback

**Goal:** parallel fan-out with per-agent models, and survival of an outage.

- `agents/definition.py`, `agents/discovery.py` [SUB-1, SUB-2]
- `agents/spawn.py` — fan-out group, cap, depth, cycle guard [SUB-5, SUB-6, SUB-10]
- `task` tool re-entering the loop
- Fresh context, summary return, transcript persisted [SUB-3, SUB-4]
- Policy narrowing and taint propagation [PERM-8], budget inheritance [SUB-7, BUD-4]
- Multi-row status bar [SUB-9]
- Routing rules and `edgar route explain` [ROUTE-2..4, ROUTE-6, ROUTE-9]
- `providers/fallback.py`, with reasoning off after a family switch [ROUTE-7, ROUTE-10, PRV-13]
- `isolation: worktree` for write-capable subagents [SUB-11] *(Should)*
- `edgar agents list|validate`, example agents in `examples/`

**Done when:** three subagents on three different providers run in parallel, each
within its own allowlist and budget, with cost attributed per agent and their
permission prompts asked one at a time; a simulated outage falls back sideways
across families and the next request is accepted.

---

## M10 — Extensions, hooks, plugins, embedding

**Goal:** the tinkerer packages and shares; other programs build on edgar.

- `extensions/manifest.py`, `discovery.py`, `edgar ext list|validate|add` [EXT-1..3, EXT-8]
- `extensions/hooks.py` — events, veto-only `pre_tool`, fail closed [EXT-4..7]
- Provider plugins through `edgar.providers` entry points [PRV-14]
- `sandbox/` port: `none`, `bwrap`, `seatbelt`, `container` [PERM-15] *(Should)*
- Deterministic skill activation, description lint [SKL-17]
- `edgar.testing.contract` — the contract kit for plugin authors
- `edgar.run()` embedding API [EXT-9]
- Remaining slash commands [CLI-14]

**Done when:** a user builds an extension with a command tool, a skill, an agent
and a hook from the docs alone; a plugin provider in a separate package passes the
contract kit; a failing `pre_tool` hook denies; and startup time is unchanged.

**Resolves:** OQ-9 (`ext update`).

---

## M11 — Init, doctor, docs · **v1.0 release**

**Goal:** a good first ten minutes, and a teaching artifact that is actually one.

- `edgar init` and `/init` — templates, credential detection, no secrets on disk [CFG-4, CFG-6]
- `edgar doctor` — credentials, connectivity, MCP, extensions, trust, DB integrity,
  cloud-synced directory warning, sandbox recommendation; `--network` lists every
  reachable host [CFG-5, PRV-15]
- `config show --resolved` with grant origins [CFG-2]
- `edgar sessions compact ID` [CTX-10]
- `docs/TOUR.md` — guided walk through BLUEPRINT §18
- `docs/COOKBOOK.md` — piping, command and HTTP tools, subagents, skills,
  extensions, hooks, a devcontainer for untrusted work
- `docs/EXTENDING.md` — add a provider, a tool, an agent, a skill, an extension
- `docs/DEPENDENCIES.md` — every dependency with its import cost [NFR-5]
- `examples/` executed in CI; docs-coverage test [NFR-10]
- Release automation: PyPI, PyApp binaries per platform, Docker image
- **Verification: hand the docs to someone and time them adding a provider**

**Done when:** the v1.0 success criteria in PRD §11 are met, the formats in EXT-10
are documented as stable, and `src/` is under 8,000 LOC.

---

# v2 — 2.0

v2 code lives in `edgar.learning`, `edgar.controller`, `edgar.schedule` and
`providers/escalation.py`. From M12 on, CI also deletes those packages and runs
the v1 suite [NFR-12].

## M12 — Learning foundations

**Goal:** the harness learns from what you type and what breaks, safely.

- `learning/experience.py` — telemetry as a bus subscriber, including verification
  result, skills loaded and task shape [MEM-18]; `edgar stats` [MEM-19]
- `learning/learner.py` — autolearn from typed text only [MEM-8, MEM-9]
- `learning/error_facts.py` — templated facts from `ErrorRecord`s [MEM-22]
- `learning/history.py` — `history.md`, out-of-band condensing, rotation,
  `history show|distill` (pending only) [MEM-12..14, MEM-16, MEM-17]
- Property test: no generated trajectory produces an active fact whose provenance
  is not `user`, `user-prompt`, `user-feedback` or `error-template`

**Done when:** a typed correction in session 1 changes behaviour in session 4 with
no `/remember`; a fetched page saying "remember X" never produces an active fact;
the v1 suite is green with `learning/` deleted.

**Resolves:** OQ-1 (history gitignored or committed).

---

## M13 — Controller

**Goal:** self-management that cannot hurt you.

- `controller/triggers.py` — deterministic checks [CTRL-1]
- Trigger on threshold, opt-in always-on [CTRL-2]
- Limited tool set [CTRL-3]
- `controller/proposals.py` — the eight-action whitelist, schema-validated [CTRL-4, CTRL-5]
- `controller/apply.py` — dry-run default, mutation log, revert [CTRL-6, CTRL-7, CTRL-10]
- Tighten-only enforcement [CTRL-8]
- `switch_model` constrained to escalation chain or routing targets [ROUTE-8]
- `propose_instruction` — diff to `.edgar/proposals/`, never a write [CTRL-12]
- Never fails the turn [CTRL-11]
- `edgar controller log|revert|apply`

**Done when:** every whitelist action is exercised with fabricated proposals, a
proposal attempting to loosen policy or naming an arbitrary model is rejected and
logged, no controller path can write `AGENTS.md` or a fact, and the v1 suite is
green with `controller/` deleted.

---

## M14 — Skill synthesis

**Goal:** verified procedures become skills.

- `learning/synthesis.py` — triggers in the controller gate; outline input with
  `ErrorRecord`s [SKL-8, SKL-9]
- `skills.synthesis = off | propose | auto`, default `propose` [SKL-10]
- `auto` writes to `learned/` only, verified triggers only; disclaimer [SKL-11, SKL-13]
- Provenance frontmatter, `[learned]`, `skills list --learned`, `skills forget` [SKL-12]
- Per-skill `HISTORY.md` observations and `skills distill` [SKL-6, SKL-14]
- Fixed body shape checked by `skills validate` [SKL-16]
- `learning/curator.py` and `skills curate`, off by default [SKL-15] *(Should)*

**Done when:** J8 holds with the fake provider; a test asserts no tool output and
no error text reaches the synthesiser; in `auto` mode a property test over
generated trajectories shows no hand-authored skill file ever changes.

**Resolves:** OQ-6 (task shape definition).

---

## M15 — Escalation and route suggest

**Goal:** a weak model that fails gets help, visibly and within limits.

- `providers/escalation.py` — upward only, capped, announced [ROUTE-5, ROUTE-10]
- Reasoning off after a family switch [PRV-13]
- Budget-aware downgrade before abort [ROUTE-11]
- `edgar route suggest` over experience telemetry, print-only [ROUTE-12]
- Responses API adapter if the eval set shows the gap (OQ-8)

**Done when:** an escalation is visible in the status bar when a weak model fails
twice, never moves down the chain, and never exceeds `max_escalations`.

**Resolves:** OQ-8.

---

## M16 — Scheduling · **v2.0 release**

**Goal:** unattended runs that cannot run away.

- `schedule/parser.py`, `schedule/due.py` — pure [SCH-4, SCH-5]
- `schedule/tick.py` — overlap prevention, catch-up policy [SCH-6, SCH-7]
- `schedule/install.py` — cron, launchd, Task Scheduler [SCH-3]
- `schedules.toml`, `edgar schedule add` appending from a template [SCH-1, SCH-12]
- Per-entry mode, agent, model, allowlist, verify [SCH-8]
- Run transcripts, `session_end` hook [SCH-9, SCH-10]
- `schedule_self` in the `self_schedules` table, with guardrails [SCH-11]

**Done when:** frozen-clock tests cover every catch-up policy, overlap is
prevented, a self-schedule never touches `schedules.toml`, and the v2.0 success
criteria in PRD §11 are met with `src/` under 11,000 LOC.

---

## Past v2

Ordered by expected value, not commitment.

1. **Notifications** — desktop, webhook, Teams; a `session_end` hook covers the gap
2. **Concurrent read-only tool calls within one response** — calls run in order
   today (TOOL-12); revisit with ordering guarantees if latency demands it
3. **OpenAPI import** — generate HTTP tools from a spec
4. **Vector or graph retriever plugins** — through the retriever port, if one beats
   multi-term FTS on the eval set (ADR-0024)
5. **TUI mode** — behind a flag, never replacing line-oriented output
6. **Shared or remote memory** — team-level facts
7. **`git` and language-server tools** — `shell` and command tools cover the common cases
8. **Homebrew and Scoop manifests** — when someone asks
9. **Image and multimodal input**
10. **Prompt-caching optimisation** across providers, not just Anthropic

## Never

Listed so the question stops recurring. Full rationale in PRD §5.2.

MCP server mode · server/daemon/HTTP API · RAG or vector index · multi-user or RBAC
· GUI · fine-tuning · plugin marketplace or skill hub (extensions are copied, never
installed from an index) · messaging gateway · user modelling · memory nudges in
the prompt · agent-to-agent network protocols · racing to support fifty providers
