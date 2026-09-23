# Roadmap

Twenty-three milestones in five tiers ([ADR-0015](adr/0015-release-tiers.md),
re-tiered by [ADR-0057](adr/0057-daily-driver-before-learning.md)). Each
milestone ships something that works, is tested, is documented, **and has its
tour**: the last item of every milestone is the tour page or stops for what it
built. Nothing is "done later". Each tier ends in a release.

| Tier | Name | Milestones | Release | Promise | Source budget |
|---|---|---|---|---|---|
| **Core** | | M0–M6 | 0.x | Read it in an afternoon, use it every day | ≤ 5,000 LOC |
| **v1** | | M7–M11 | 1.0 | Extensible and remembers; extension formats frozen | ≤ 8,000 LOC |
| **v2** | the daily driver | M18–M22 | 2.0 | Work in it all day: code, git, subagents, tools, search, images | ≤ 9,500 LOC |
| **v3** | learning | M12–M15 | 3.0 | Learns from what you type and what breaks; removable | ≤ 12,000 LOC |
| **v4** | unattended | M17, M16 | 4.0 | Runs unattended under a signed scope; removable | ≤ 13,000 LOC |

LOC means lines of code: non-blank lines that are not only a comment. Docstrings
count; comments do not ([ADR-0040](adr/0040-written-to-be-read.md)).

**Why this order.** v1 is finished and has never been used for a day's work. The
tier ADR-0015 planned next learns from corrections and verified runs, and an
unused tool has nothing to learn from. So the daily driver comes first, the
learning layer after it, and the parts that run unattended last
([ADR-0057](adr/0057-daily-driver-before-learning.md)). v2 extends Core and v1
packages and is not removable; v3 and v4 are, and CI proves it [NFR-12].

## Status

Milestone IDs keep their numbers; the order of work is **M0, M1, M2, M4, M3, M5,
M6**, then v1 ([ADR-0033](adr/0033-replan-after-m2.md)), then **M18, M19, M20,
M21, M22** (v2), then **M12, M13, M14, M15** (v3), then **M17, M16** (v4): the
capability broker comes before scheduling, which carries the 4.0 release
([ADR-0039](adr/0039-capability-broker.md)). The day-by-day record is
[`JOURNAL.md`](JOURNAL.md); user-visible changes are in
[`CHANGELOG.md`](../CHANGELOG.md); the coder's starting point is
[`HANDOFF.md`](HANDOFF.md).

| Milestone | Status | Shipped in |
|---|---|---|
| M0 Skeleton | Done | 0.0.1, 0.0.2 |
| M1 The loop | Done | 0.1.0 |
| M2 Real providers | Done | 0.1.0 |
| M4 REPL, streams, model picker | Done | 0.1.0 |
| M3 Tools, permissions, verify, custom tools, trust | Done | 0.1.0 |
| M5 Context and sessions | Done ([ADR-0038](adr/0038-context-and-sessions-as-built.md)) | 0.1.0 |
| M6 Skills, Core release | Done ([ADR-0041](adr/0041-skills-as-built.md)) | 0.1.0 |
| M7 Memory and session search | Done ([ADR-0045](adr/0045-memory-as-built.md), [ADR-0046](adr/0046-forks-saves-and-the-daily-cap.md)) | 0.1.0 |
| M8 MCP | Done ([ADR-0047](adr/0047-mcp-as-built.md), [ADR-0048](adr/0048-signing-in-as-built.md)) | 0.1.0 |
| M9 Subagents, routing rules and fallback | Done ([ADR-0054](adr/0054-m9-subagents-as-built.md)) | 1.0 |
| M10 Extensions, hooks, plugins, embedding | Done ([ADR-0055](adr/0055-m10-extensions-as-built.md)) | 1.0 |
| M11 Init, doctor, docs | Done · 1.0 ([ADR-0056](adr/0056-m11-as-built.md)) — PRD §11's two human criteria still open | 1.0 |
| M18 Tours for v1 and the map | Done ([ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md)) | 2.0 |
| M19 Working state | Done ([ADR-0059](adr/0059-m19-working-state-as-built.md)) | 2.0 |
| M20 Seeing and searching | Done ([ADR-0060](adr/0060-m20-seeing-and-searching-as-built.md)) | 2.0 |
| M21 Isolation | Done ([ADR-0061](adr/0061-m21-isolation-as-built.md)) — the sandbox confines writes and the network, **not reads**; see ADR-0061 §2 | 2.0 |
| M22 Inspection, 2.0 release | Code done ([ADR-0062](adr/0062-m22-inspection-commands-as-built.md)) — **the 2.0 release is not started**, `edgar.testing.contract` [PRV-14] dropped to v3 for budget, and the two human "Done when" criteria are open | 2.0 |
| M12 Learning foundations | Done 2026-09-17 ([ADR-0063](adr/0063-m12-learning-foundations-as-built.md)) | 3.0 |
| M13 Controller | Done 2026-09-18 ([ADR-0064](adr/0064-m13-controller-as-built.md)) | 3.0 |
| M14 Skill synthesis | Done 2026-09-19 ([ADR-0065](adr/0065-m14-skill-synthesis-as-built.md)) | 3.0 |
| M15 Escalation, route suggest | Done 2026-09-23 ([ADR-0066](adr/0066-m15-escalation-as-built.md)); ROUTE-11, ROUTE-12 and OQ-8's adapter deferred, priced out at 104 LOC remaining | 3.0 |
| M17 Capability broker | In progress on `feat/m17-capability-broker` — pure core [CAP-2, CAP-5, CAP-9], the `pre_tool` veto stage [CAP-3, CAP-6], intent creation [CAP-1], `--scope`/`/scope` (live end to end) and `task` attenuation on delegation [CAP-9] built and tested; the controller's `tighten_policy` (CTRL-8), receipt, its CLI command, config and tour are not started; 20 LOC of headroom left outside removable packages, see `docs/HANDOFF.md` | 4.0 |
| M16 Scheduling | Planned | 4.0 |

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
  prefix and its test, pinned sections [CTX-1, CTX-5, CTX-15, CTX-17]
- `context/tokens.py` — exact plus approximate [CTX-9]
- `context/compact.py` — S1 elide, S2 summarise, S3 overflow, hysteresis [CTX-3, CTX-6, CTX-11, CTX-12]
- ~~`edgar context show`~~ moved to M11 ([ADR-0038](adr/0038-context-and-sessions-as-built.md)) [CTX-2]
- `/compact` with optional focus [CTX-7]
- `storage/transcript.py` — JSONL with compaction records [CTX-14, ADR-0010]
- `--resume`, `--continue`, `edgar sessions list|show|rm` [CLI-11]
- Session commands as appended records: `/new /clear /reset /undo /retry
  /title /sessions /load ID` [CLI-25, CLI-26, CLI-28, ADR-0029]; `/save`, loading a
  saved file and `edgar --load` moved to M7 ([ADR-0037](adr/0037-core-fits-in-5000.md)),
  and `/history` with them ([ADR-0038](adr/0038-context-and-sessions-as-built.md))
- `personality.md`, user and project scope, in `edgar prompt show` [CTX-19, ADR-0030]
- The control-file hash stored at session end, and the warning when it changed
  (moved from M3) [PERM-12]
- Turn and session cost caps [BUD-2, BUD-3], `/cost` [BUD-6]; the daily cap and
  `edgar cost` moved to M7
- Idempotency, overflow and spill tests [CTX-8]

**Done when:** a 200-turn session with heavy tool use autocompacts repeatedly,
including inside a single long tool-calling turn, without ever producing a
transcript that fails the invariant; most compactions use S1 only; `--resume`
rebuilds the compacted view; the prefix stays byte-identical
across every request between compactions; and pinned content that alone exceeds
the window raises `ContextOverflow` with a hint; `/undo 2` followed by
`--resume` shows exactly the conversation the user saw. `src/` stays under the
Core budget with room for M6 (about 250 lines).

---

## M6 — Skills and the Core release · **Core release**

**Goal:** skills, and a release people can fork. (Custom tools and trust moved to
M3, [ADR-0033](adr/0033-replan-after-m2.md); `edgar login` to M8,
[ADR-0037](adr/0037-core-fits-in-5000.md).)

- Added after M6 was met: keyless sign-in through the cloud's own CLI, `api_key_command` [PRV-20, [ADR-0044](adr/0044-keyless-cloud-sign-in.md)]
- `skills/discovery.py` (PyYAML, lazily) and the `skill` tool, which loads the body [SKL-1..5]; a skill's `verify` moves to v1 ([ADR-0041](adr/0041-skills-as-built.md))
- `edgar tools list|describe`, `edgar skills list|validate` [SKL-7]
- Collision order with startup warning (without MCP and extensions yet) [TOOL-9]
- Examples of each in `examples/`
- Short docs: README quick start, `docs/COOKBOOK.md` first recipes

**Done when:** J3 and J9 pass their acceptance tests end to end; `src/` is under
5,000 LOC. *Met on 2026-09-14: both journeys run through the real CLI in
`tests/e2e/test_cli.py`, and Core is 4,966 lines of code.*

**Release:** 0.1 to PyPI. From here people can use and fork edgar.

---

# v1 — 1.0

## M7 — Memory and session search

**Goal:** the harness remembers what you tell it, and finds what it saw.

- `memory/store.py` with pending and active states, FTS5 [MEM-3, MEM-6] (`Fact` lives in the store, ADR-0045)
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
- `/save`, loading a saved file, `edgar --load` [CLI-25]; the daily cost cap
  [BUD-2] (both moved from M5, [ADR-0037](adr/0037-core-fits-in-5000.md)); `/history`
  [CLI-25] and `edgar cost` [BUD-6] (moved from M5, [ADR-0038](adr/0038-context-and-sessions-as-built.md))

**Done when:** a fact saved in session 1 changes behaviour in session 4 and is
editable and revertible; a declined proposal is never injected; a fact saved
mid-session does not change the prompt prefix until the next session. *Met on
2026-09-14: `tests/integration/test_remembering.py` shows a fact reaching every
later session's prompt and never its own, and a declined one reaching neither a
prompt nor `recall`; edit and undo are in `tests/unit/test_memory.py`. v1 is at
5,802 of 8,000 lines of code.*

---

## M8 — MCP

**Goal:** the ecosystem, lazily.

- ✅ `tools/mcp/` — stdio and Streamable HTTP, discovery, lazy spawn [TOOL-7, TOOL-8]
- ✅ Namespacing `mcp__server__tool`, collision order [TOOL-9]
- ✅ MCP results untrusted, annotations ignored by `decide()` [TOOL-13]
- ✅ Deferred tool schemas and `tool_search` [TOOL-15]
- ✅ Project MCP servers require trust [PERM-13]
- ✅ `edgar mcp list|test`
- ✅ `/browser`: the `[browser]` preset, a command tool or an MCP server spawned on
  demand [CLI-29, ADR-0029, ADR-0036]
- OAuth for remote servers: OAuth 2.1 with PKCE, tokens in the keyring [TOOL-7,
  ADR-0032], moved from v2
- `edgar login PROVIDER` / `edgar logout`, on the same OAuth code: providers that
  issue API keys that way (OpenRouter first), the key in the keyring and redacted
  everywhere [PRV-18, CFG-6], moved from M6 ([ADR-0037](adr/0037-core-fits-in-5000.md))
- GitHub Copilot provider: `edgar login github-copilot` by device flow under edgar's
  own OAuth app, `github-copilot/<model>` as a quirks row, the subscription's models
  in `edgar models` [PRV-19, ADR-0043] *(Should; ships only once GitHub's terms are
  confirmed and the OAuth app is registered)*

**Done when:** a stdio server and a Streamable HTTP server both work, startup time
is unchanged with five servers configured, an MCP result taints the session, and
forty configured MCP tools cost no more than the schema budget per request.

*2026-09-14: all four hold ([ADR-0047](adr/0047-mcp-as-built.md)); the OAuth and
`edgar login` items above are what is left of M8. v1 is at 6,419 of 8,000 lines
of code.*

---

## M9 — Subagents, routing rules and fallback

**Goal:** parallel fan-out with per-agent models, and survival of an outage.

- `agents/definition.py`, `agents/discovery.py` [SUB-1, SUB-2]
- `agents/spawn.py` — fan-out group, cap, depth, cycle guard [SUB-5, SUB-6, SUB-10]
- `task` tool re-entering the loop
- Fresh context, summary return, transcript persisted [SUB-3, SUB-4]
- Policy narrowing and taint propagation [PERM-8], budget inheritance [SUB-7, BUD-4]
- Multi-row status bar [SUB-9]
- Routing rules [ROUTE-2..4, ROUTE-6]
- `providers/fallback.py`, with reasoning off after a family switch [ROUTE-7, ROUTE-10, PRV-13]
- Example agents in `examples/`

Plan mode and the `todo` tool [CLI-20, TOOL-14, CTX-18], `edgar route explain`
[ROUTE-9] and `edgar agents list|validate` moved to v2 ([ADR-0053](adr/0053-what-1-0-actually-ships.md)). Plan mode's
second move — ADR-0037 took it from M5 to M9 — and the reading is that it is not
part of v1; `--mode read-only` is what 1.0 has instead.

**Done when:** three subagents on three different providers run in parallel, each
within its own allowlist and budget, with cost attributed per agent and their
permission prompts asked one at a time; a simulated outage falls back sideways
across families and the next request is accepted.

`isolation: worktree` for write-capable subagents [SUB-11] moved to v2
([ADR-0050](adr/0050-trim-should-items-from-v1.md)): every subagent runs in the
parent's own working copy in v1.

*2026-09-14: `agents/definition.py`, `agents/discovery.py` and `agents/spawn.py`
are built, and the `task` tool re-enters `run_turn` with a fresh session, a
narrowed policy and an inherited budget cap; `cli/setup.py` wires it in whenever
an agent is discovered. Depth ceiling, cycle guard and policy narrowing
[SUB-6, SUB-10, PERM-8] are enforced; consecutive `task` calls still run one at
a time, `SpawnLimits.max_parallel` is read but not yet a real cap. Still open:
fan-out concurrency and the multi-row status bar it needs [SUB-9], `edgar route
explain`, `edgar agents list|validate`, example agents, plan mode and the `todo`
tool. v1 is at 7,364 of 8,000 lines of code.*

*2026-09-15: consecutive `task` calls fan out [TOOL-12]. `core/loop.py`'s own
`_run_tools()` had no room left under its 200-line cap, so the grouping and the
`asyncio.gather` moved to `tools/execute.py`'s new `execute_many()`, bounded by
an `asyncio.Semaphore` sized from the `task` tool's own
`SpawnLimits.max_parallel`; loop.py keeps only the bookkeeping (verify's
`acted` flag, session tainting), replayed in call order once each result lands
so it never races. Still open: the multi-row status bar concurrent subagents
need [SUB-9], `edgar route explain`, `edgar agents list|validate`, example
agents, plan mode and the `todo` tool. v1 is at 7,398 of 8,000 lines of code.*

*2026-09-15: the simplification pass ADR-0053 owed took v1 to 7,292 of 8,000
lines of code (106 saved, nothing cut), leaving 708 for SUB-9, example agents,
M10 and M11. It also found `check_capabilities` [ROUTE-6] tested but never
called; wiring it is part of closing M9.*

---

## M10 — Extensions, hooks, plugins, embedding

**Goal:** the tinkerer packages and shares; other programs build on edgar.

- `extensions/manifest.py`, `discovery.py`, `edgar ext list` [EXT-1, EXT-2, EXT-3 in part, EXT-8]
- `extensions/hooks.py` — events, veto-only `pre_tool`, fail closed [EXT-4..7]
- Provider plugins through `edgar.providers` entry points [PRV-14]
- `shell.sandbox` keeps its `none | bwrap | seatbelt | container` type; only
  `none` runs anything in v1, `doctor` recommends no backend — the `bwrap`,
  `seatbelt` and `container` backends [PERM-15] move to v2
  ([ADR-0050](adr/0050-trim-should-items-from-v1.md))
- Deterministic skill activation, description lint [SKL-17]
- A skill's `verify` command as a verification source, authorised like activation [SKL-1, VER-1, ADR-0041]
- `edgar.run()` embedding API [EXT-9]. Design it for the caller described in
  [ADR-0051](adr/0051-controlling-edgar-from-elsewhere.md): one program owning many
  sessions across many project directories, starting turns nobody is watching, and
  answering permission prompts out of band
- Remaining slash commands [CLI-14]

**Done when:** a user builds an extension with a command tool, a skill, an agent
and a hook from the docs alone; a plugin provider in a separate package passes the
contract kit; a failing `pre_tool` hook denies; and startup time is unchanged.

`edgar skills audit` [SKL-18] moved to v2
([ADR-0050](adr/0050-trim-should-items-from-v1.md)): `ext add` [EXT-3] copies a
skill in unaudited in v1, the conformance and danger checks stay manual until
v2 wires SKL-18 into it.

**Resolves:** OQ-9 (`ext update`).

*2026-09-15: M10 is done ([ADR-0055](adr/0055-m10-extensions-as-built.md)).
Extensions, hooks and provider plugins had landed earlier; this pass closed
out deterministic skill activation wired into both CLI paths [SKL-17], a
loaded skill's own `verify:` command taking its place in VER-1's precedence
chain, `edgar.run()` as the embedding API [EXT-9] with every non-trivial
import deferred inside its body so a bare `import edgar` stays on the NFR-1
budget, and the remaining slash commands `/agents`, `/skills`, `/tools`
[CLI-14]. v1 is at 7,918 of 8,000 lines of code — 82 left for M11.*

---

## M11 — Init, doctor, docs · **v1.0 release**

**Goal:** a good first ten minutes, and a teaching artifact that is actually one.

The first ten minutes today: `edgar models`, get bounced because no key is set,
`edgar login PROVIDER`, `edgar models` again. It should be one path that never
dead-ends, with Enter the right answer at every step.

- ~~`edgar init` and `/init`~~ done — templates, credential detection, no secrets
  on disk [CFG-4, CFG-6]. It writes a working, commented `config.toml` with the
  choices already made, never blanks; it is the only thing that writes config,
  and it still refuses to edit a file that already exists
  ([ADR-0034](adr/0034-model-picker.md))
- ~~`edgar` with nothing configured offers to run that setup instead of erroring~~ done
- ~~`edgar doctor`~~ done — credentials, connectivity and the cloud-synced directory
  warning [CFG-5, PRV-15]. Its MCP, extension, trust, tick and DB-integrity checks
  and `--network` move to v2 ([ADR-0053](adr/0053-what-1-0-actually-ships.md)); no sandbox recommendation either, since
  only the `none` backend exists ([ADR-0050](adr/0050-trim-should-items-from-v1.md))
- ~~`docs/TOUR.md`~~ done early as [A Tour of the Harness](https://vespassassina.github.io/edgar/),
  published to GitHub Pages ([ADR-0040](adr/0040-written-to-be-read.md)); M11 checks
  it covers all of v1
- ~~`docs/COOKBOOK.md`~~ done — piping, command and HTTP tools, subagents,
  skills, extensions, hooks, a devcontainer for untrusted work, plus recipes
  for `init`/`doctor`, permission grants and `login`/`logout` found missing by
  the docs-coverage test below
- ~~`docs/EXTENDING.md`~~ done — a tool, a subagent, a skill, an extension, a
  provider, each grounded in the source that actually implements it
- ~~`docs/DEPENDENCIES.md`~~ done — every dependency with its measured import
  cost [NFR-5]; names ADR-0019's `rich` mismatch rather than hiding it
- ~~`examples/` executed in CI; docs-coverage test~~ done — [NFR-10]: an example
  extension exercised by `tests/e2e/test_cli.py::test_j11_…`, and
  `tests/unit/test_docs_coverage.py` checks every `edgar.cli.admin.USAGE`
  subcommand and every v1 `Config` section against the docs a first-week user
  would open. ADR-0056 has the design decisions
- ~~Release automation: PyPI, PyApp binaries per platform, Docker image~~ done —
  PyPI trusted publishing already shipped; `pyapp` and `docker` jobs added to
  `.github/workflows/release.yml`, unverified by an actual release run (ADR-0056)
- A cold subagent, given only `EXTENDING.md`/`COOKBOOK.md` and told not to
  open `src/`, added `examples/tools/weather.toml` (an HTTP tool, no auth,
  wttr.in) on its first attempt and never needed to look — a real proxy for
  half of the non-Python-user criterion below, though not the thing itself
- **Still open: hand the docs to an actual person and time them adding a
  provider.** The subagent run above is evidence the tool half of the
  non-Python-user criterion is achievable from docs alone, but an agent
  that already reads TOML fluently is not "a non-Python user", and nothing
  here substitutes for "verified by trying it on someone" for a new
  provider either. Both of PRD §11's human-verification criteria stay open
  until an actual outside person does it

`edgar sessions compact ID` [CTX-10] moved to v2
([ADR-0050](adr/0050-trim-should-items-from-v1.md)): `/compact` inside the REPL
(already Core) is unaffected.

`config show --resolved` [CFG-2] and `edgar context show` [CTX-2] also moved to
v2 ([ADR-0053](adr/0053-what-1-0-actually-ships.md)) — the second move for `context show`, which ADR-0038 brought here
from M5. Config still carries provenance internally; what is missing is the
command that prints it.

**Done when:** the v1.0 success criteria in PRD §11 are met, the formats in EXT-10
are documented as stable, and `src/` is under 8,000 LOC.

*2026-09-15: `edgar init`/`/init` and `edgar doctor` are done. Adding them briefly
pushed v1 over budget (8,041/8,000); closed by moving explanatory docstring prose
into free `#` comments across six files, no behaviour change. v1 is at exactly
8,000 of 8,000 lines of code — no headroom left for anything that isn't a `.py`
file.*

*2026-09-15, later the same session: the docs trio, the example extension, the
docs-coverage test [NFR-10] and release automation are all done
([ADR-0056](adr/0056-m11-as-built.md)). `src/` is untouched, still exactly
8,000/8,000. M11 and v1.0 are code-complete; the two success criteria in PRD §11
that need an actual outside person trying the docs are still open, and stay open
until someone does that.*

---

# v2 — 2.0, the daily driver

Everything a person needs to work in edgar all day, on real code, with git,
subagents, tools, web search and images ([ADR-0057](adr/0057-daily-driver-before-learning.md)).
v2 extends Core and v1 packages, so it is not removable; its budget is
**≤ 9,500 lines of code** for all of `src/`, about 1,250 more than v1's 8,000.
Every estimate below is an order of magnitude, measured against subsystems
already built; if the total does not fit, the last items of M22 move to v3, the
number stays.

| Milestone | Adds to `src/` (est.) | Running total |
|---|---|---|
| M18 Tours for v1 and the map | 0 | 8,000 |
| M19 Working state | 374 (built) | 8,374 |
| M20 Seeing and searching | 218 (built) | 8,592 |
| M21 Isolation | 277 (built) | 8,869 |
| M22 Inspection, 2.0 release | 436 (built, PRV-14 dropped) | 9,305 |

**How to read a v2 milestone.** Each item names the files it touches, the
requirement IDs it closes, the test that proves it and its size. Items are
ordered so a coding session can take the first unchecked one, build it with its
test, update the tour stop named in the last item, and stop. The friction list
from the dogfood week ([`HANDOFF.md`](HANDOFF.md), step 0) reorders items
inside a milestone; it does not add to the budget.

**Before M18, two tasks that are not milestones** (details in
[`HANDOFF.md`](HANDOFF.md)): tag v1.0 and watch the first real release run, since
the `pyapp` and `docker` jobs have never executed; then a week of using edgar on
edgar with a real model, journalling every friction.

---

## M18 — Tours for v1, and the map

**Done**, 2026-09-16 ([ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md)).
The tour now has a page per v1 feature, six new Core stops, a generated
[map](tour/map.html) refreshed by `just map`, and a test that fails when a file
under `src/edgar` has no stop on any page. `src/` is untouched at 8,000/8,000.

**Goal:** a student can learn every v1 feature by following a tour, and see the
whole harness on one map. Writes no `src/` code; changes `docs/tour/`, `tests/`
and a generator script.

The Core tour ([`docs/tour/index.html`](tour/index.html)) has 19 stops in six
stages. v1 has one summary stop per milestone (s20–s24), and 32 of the 78 source
files under `src/edgar` (excluding `__init__.py`) have no stop at all, the whole
`auth/` package among them.

- **Shared tour assets.** Move the tour's page CSS and the small script that
  builds the contents list out of `index.html` into `docs/tour/tour.css` and
  `docs/tour/tour.js`; every tour page links them relatively. The artifactkit
  theme block stays where it is. `test_tour.py`'s "page loads its own files"
  check runs over every page.
- **One tour page per v1 feature, in Core's format** (stages, stops with
  `data-files`, a "look for" list per stop, one diagram, a size table):
  - `docs/tour/memory.html` (M7): the boundary (`memory/store.py`,
    `memory/redact.py`), recall (`memory/retriever.py`, `memory/recall.py`),
    the markdown round trip (`memory/markdown.py`), the commands
    (`cli/memory.py`), forks and saves (`storage/transcript.py` records)
  - `docs/tour/mcp.html` (M8): lazy start (`tools/mcp/client.py`,
    `tools/mcp/stdio.py`, `tools/mcp/http.py`, `tools/mcp/schema.py`), deferred
    schemas (`tools/builtin/tool_search.py`), signing in (`auth/oauth.py`,
    `auth/store.py`, `auth/keys.py`, `auth/mcp.py`)
  - `docs/tour/agents.html` (M9): re-entering the loop (`tools/builtin/task.py`,
    `agents/definition.py`, `agents/discovery.py`, `agents/spawn.py`), fan-out
    (`tools/execute.py::execute_many`), the multi-row status bar, three model
    mechanisms kept apart (`providers/routing.py`, `providers/fallback.py`)
  - `docs/tour/extensions.html` (M10): the manifest (`extensions/manifest.py`,
    `extensions/discovery.py`), hooks that veto (`extensions/hooks.py`),
    provider plugins (`providers/registry.py` entry points), skill activation
    (`skills/discovery.py`), `edgar.run()` (`__init__.py`)
  - `docs/tour/index.html`: Part II's five stops become short summaries that
    link to the pages; Part III's heading and pills read v3 and v4 per ADR-0057
- **Core's own missing stops**, added to `index.html` in the stage they belong
  to: `core/aside.py`, `core/errors.py`, `context/prompts.py`,
  `context/tokens.py`, `permissions/control.py`, `config/schema.py`,
  `config/init.py`, `config/doctor.py`, `storage/db.py`, `tools/spill.py`,
  `tools/registry.py`, `providers/registry.py`, `providers/http.py`,
  `providers/pricing.py`, `providers/fake.py`, `cli/main.py`, `cli/admin.py`,
  `cli/models.py`, `cli/trust.py`, `__main__.py`. Files that exist under other
  names are named as they are; this list was taken from the tree at `05b1ab2`.
- **The no-orphan test.** `tests/unit/test_tour.py` collects `data-files` from
  every `docs/tour/*.html`, takes the set difference against every `.py` under
  `src/edgar` except `__init__.py`, and asserts it is empty. From here on a new
  module without a stop fails CI, like the size budget does.
- **The map.** `scripts/tour_map.py` walks `src/edgar` and writes
  `docs/tour/map.json`: one node per tier, package and file with `path`,
  `kind`, `loc` (from `tests/support/budget.py::count_loc`), `summary` (the first
  line of the file's opening `#` comment block), `stop` (the tour page and
  anchor whose `data-files` names it), `status` (`built`, or `planned` for a
  file named only by a planned stop) and `port` (true for `providers/base.py`,
  `tools/base.py`, `skills/discovery.py`, `sandbox/base.py`,
  `memory/retriever.py`, `cli/render.py`, ADR-0022's six ports).
  `docs/tour/map.html` renders it as an exploded tree, root to tiers to packages
  to files, inline SVG and CSS, no library, tree only and no flows: hover shows
  the summary and size, click opens the stop, planned nodes are dashed, ports
  are marked, chip width follows `loc`, and the tree collapses to one column on
  a phone. `just map` regenerates the JSON; `test_tour.py` regenerates it in
  memory and asserts the committed file is identical.
- **Stale lines fixed**: the tour header's "Planned M9 to M17", Part II's pill,
  README's status paragraph and "Coming in 1.0" section, all of which still say
  M9–M11 are unbuilt.
- **Tour delivery for M18 itself:** the map is it; and `index.html`'s header
  links every page.

**Done when:** the no-orphan test passes; every page opens from GitHub Pages
with no console error; `map.json` is current in CI; a reader can go from the map
to any file's stop in one click.

---

## M19 — Working state · DONE 2026-09-17

Built in six commits, `41052a8..c73c0f7`, one per item;
[ADR-0059](adr/0059-m19-working-state-as-built.md) records the decisions.

**Goal:** the things a person reaches for in the first hour of real work and
does not find. About 340 lines of code.

- **`@path` attachments** [CLI-3], ~60. In the REPL and `-p`, a token `@path`
  in a typed prompt attaches that file's text to the user message as `attached`
  content (the field exists in `core/message.py`, §3.1), which by type never
  reaches the learning path [MEM-9]. Text files only in this milestone (images
  arrive in M20); a directory or a binary is refused with a message naming the
  path and what is accepted; content over `tools.max_output_tokens` spills like
  tool output (S0). Test: a prompt with `@README.md` produces one user message
  whose `attached` text is the file, `@missing` is a user-facing error not an
  exception, and `@.edgar/config.toml` obeys the control-file rule in the
  current mode.
- **Plan mode and the `todo` tool** [CLI-20, TOOL-14, CTX-18], ~160.
  `context/working.py` holds the plan and the todo list as pinned working state
  just above the current turn, surviving compaction ([ADR-0025](adr/0025-working-state.md));
  `tools/builtin/todo.py` writes it; `/plan` and `--plan` enter plan mode
  (`read-only` policy plus `sessions/<id>/plan.md`), `/go` returns to the mode
  the session had and keeps the plan pinned; `TodoUpdated` on the bus, rendered
  by the status bar. Test: a 60-turn session with compaction keeps the todo
  list byte-identical in every request; `/plan` then `write` is denied; `/go`
  restores the mode. Its third move (ADR-0037, ADR-0053); this is where it lands.
- **`edgar context show`** [CTX-2], ~40. Prints the assembled prompt for a
  session in order, one row per section with its token count, and marks the
  cache breakpoint, from `context/builder.py` without a provider call. Test:
  the rows sum to the builder's own count.
- **`edgar sessions compact ID`** [CTX-10], ~40. Runs the same stages `/compact`
  runs, on a stored session, appending a compaction record; never rewrites
  history. Test: the pairing invariant holds after it and `--resume` shows the
  compacted view.
- **`edgar config show --resolved`** [CFG-2], ~40. Every effective key with the
  file and layer it came from, secrets redacted. Test: an env override shows
  its provenance; an API key shows as `***`.
- **Tour delivery:** `docs/tour/working.html` with stops for
  `context/working.py`, `tools/builtin/todo.py`, the `@path` parser and the
  three commands; `just map`.

**Done when:** the five items above pass their tests on three platforms, and a
day of dogfooding with `@path` and `/plan` produces no journal entry about
either.

---

## M20 — Seeing and searching · DONE 2026-09-17

Built in ten commits, `e512b90..33e1d90`, one per item;
[ADR-0060](adr/0060-m20-seeing-and-searching-as-built.md) records the decisions
and flags three of them for extra review. 218 lines of code against the ~200
estimated, all in the image items; web search and git cost none, as planned.
Two deviations from the plan below, both recorded in ADR-0060 and the journal:
the contract suite's image cases assert on the request body of the existing
scenarios rather than adding cassettes, because serialising an image is entirely
outbound and no provider returns one; and the `post_tool` hook example is an
observe-only commit trail (`examples/extensions/git-trail/`) rather than a
formatter run after `edit`.

**Goal:** the agent can look at an image, search the web and use git properly.
About 200 lines of code; web search and git cost none.

- **Images** ([ADR-0052](adr/0052-media-input-in-v2.md)), ~200, in this order:
  1. `core/message.py`: `ImageBlock(media_type, ref)`, frozen and slotted like
     the other four blocks; nothing else joins the vocabulary. Test: the pairing
     invariant and compaction properties still hold with images in a unit.
  2. `tools/spill.py`: image bytes go to `sessions/<id>/blobs/` and the block
     carries the reference, never base64 in the JSONL.
  3. `providers/quirks.py`: an `images` capability row per provider; a model
     without it is refused where it is chosen, never mid-turn [ROUTE-6].
  4. `providers/openai_compat.py` and `providers/anthropic.py` serialise the
     block; `providers/fake.py` accepts it; the contract suite gains one image
     case per provider.
  5. `context/tokens.py`: cost by image geometry, per provider, so compaction
     and the caps stay right.
  6. `context/compact.py`: S1 elides an old image to a stub like a tool result.
  7. Inputs: `@photo.png` in a prompt (extends M19's parser) and the `read`
     tool on an image file both produce an `ImageBlock`; `--events` gains the
     reference.
- **Web search as an extension**, 0 lines. `examples/tools/web_search.toml`:
  an HTTP tool with the host fixed and the key from the environment, in three
  documented variants the user picks from (Brave, Tavily, a self-hosted
  SearXNG); no default host, per PRV-15. `examples/skills/web-research/SKILL.md`:
  search, then `fetch` the top hits, then answer with sources. A Cookbook recipe
  and a docs-coverage row. Verified the way the weather tool was: a cold
  subagent adds it from the docs alone.
- **Git as an extension**, 0 lines. `examples/tools/git-status.toml`,
  `git-diff.toml`, `git-log.toml`, `git-commit.toml` as command tools (argv
  templates, `git-commit` takes the message as one argument);
  `examples/skills/git/SKILL.md` with the etiquette from AGENTS.md (branch per
  topic, small commits after the check passes, imperative subject, never
  force-push, check before push); a `post_tool` hook example running the
  formatter after `edit`. A Cookbook recipe, "working with git".
- **Tour delivery:** `docs/tour/media.html` with stops for the seven image
  steps in order, and a stop each for the search and git example folders as
  files, not code; `just map`.

**Done when:** the fake provider round-trips an image through a turn and
`--resume`; a provider without `images` refuses at selection; the search and
git examples pass the examples-in-CI test; a dogfood day of research and
committing produces no journal entry about either.

---

## M21 — Isolation

**Goal:** a write-capable subagent cannot damage the working copy, and `shell`
can run in a sandbox. About 350 lines of code.

- **Worktree subagents** [SUB-11], ~150. `agents/worktree.py`: for an agent
  whose frontmatter says `isolation: worktree`, `git worktree add` under
  `.edgar/worktrees/<agent>-<session>` on a new branch, the subagent's `cwd` and
  path rules rebased there, the branch name and a diff stat in the returned
  summary, and cleanup on return (`remove` when the tree is clean, `keep`
  otherwise, both announced). Refused with a clear message outside a git repo.
  Test: two subagents writing the same file finish on two branches and the
  parent's tree is untouched; a dirty worktree is kept and named.
- **Sandbox backends** [PERM-15], ~200. The `Sandbox` port is designed
  ([BLUEPRINT §7.5](BLUEPRINT.md)) but `sandbox/` does not exist yet; create
  `sandbox/base.py` (the protocol and detection) and `sandbox/none.py`, then add `sandbox/bwrap.py` (Linux, bubblewrap: project read-write, home
  read-only, network per the permission decision) and `sandbox/seatbelt.py`
  (macOS, a generated `sandbox-exec` profile with the same shape), plus
  detection and the `doctor` line recommending the best available backend.
  `container` stays deferred (Past v4) unless the budget allows it at the end
  of M22. Core tests use the fake sandbox and run everywhere; backend tests run
  only where the backend exists, and are the one place a platform condition is
  allowed, because they test the platform. Test: with a backend on, a `shell`
  call cannot read outside the allowed roots and cannot reach the network when
  the decision says no.
- **Tour delivery:** `docs/tour/isolation.html` with stops for
  `agents/worktree.py`, `sandbox/base.py`, `sandbox/bwrap.py`,
  `sandbox/seatbelt.py` and the `doctor` line; `just map`.

**Done when:** the four tests above pass; on macOS and Linux a dogfood day with
a write-capable subagent leaves the main tree clean.

**As built** ([ADR-0061](adr/0061-m21-isolation-as-built.md)), 277 lines of code.
Two corrections to the text above, both deliberate and both flagged in the ADR:

- **"cannot read outside the allowed roots" is not what shipped.** That line
  contradicts [BLUEPRINT §7.5](BLUEPRINT.md) and PRD PERM-15, which specify a
  read-only root bind and a writable set — a *write* boundary. The backends
  confine writes and the network; a confined process can still read anything the
  user can read. A read boundary, if wanted, is its own milestone.
- **The port is `wrap(argv, …) -> list[str]`,** not `async run(…)`. `run_argv`
  stays the only process launcher, and the generated argv and profile are
  asserted on every platform.

`seatbelt` was executed for real on macOS; `bwrap` is written and its argv
asserted, but has never run. The Linux half of "done when" is still open.

---

## M22 — Inspection commands · **v2.0 release**

**Goal:** the commands that explain what edgar is doing, cut from 1.0 by
ADR-0053, and the release. About 440 lines of code; the last items yield first
if the budget is short.

- **The rest of `edgar doctor`** [CFG-5], ~140: each configured MCP server
  reachable, each extension's required commands present, the project's trust
  state, `PRAGMA integrity_check` on the DB, tick installation once M16 exists,
  and `--network` to try each provider endpoint. Every line says what it
  checked, what it found and what to do.
- **`edgar route explain [PROMPT]`** [ROUTE-9], ~35: which rule matched and why,
  from `routing.select_model()`, no provider call.
- **`edgar agents list|validate`**, ~45: the discovered agents with scope and
  model, and every frontmatter error with file and line.
- **`edgar ext validate|add`** [EXT-3] with **`edgar skills audit`** [SKL-18]
  wired in ([ADR-0042](adr/0042-skill-audit.md)), ~150: `validate` checks a
  folder against the manifest rules, `add` copies it in after `validate` and
  the skill audit both pass, `audit` prints the conformance and danger report
  and the diff it proposes, never applying it.
- ~~**`edgar.testing.contract`** [PRV-14], ~70~~ — **dropped to v3 for budget**
  ([ADR-0062](adr/0062-m22-inspection-commands-as-built.md) §6). The suite is 265
  lines of test code, so packaging it would cost about 200 lines of code against
  the tier, not 70; 195 remained. `tests/contract/test_provider_contract.py` still
  runs for every built-in provider in the meantime.
- **Release 2.0.0:** bump `pyproject.toml` and `src/edgar/__init__.py`, move
  `CHANGELOG.md`'s Unreleased under 2.0.0, tag, watch the three release jobs.
- **Tour delivery:** the commands join the Core tour's surface stage and the
  extensions tour; `just map`; `test_tour.py` green.

**Done when** ([ADR-0057](adr/0057-daily-driver-before-learning.md) decision 8):
the maintainer has worked in edgar on edgar for two weeks on a real model and
the journal lists no blocking friction; an actual outside person has done PRD
§11's two human checks; `src/` ≤ 9,500 lines of code; CI green on three
platforms.

---

# v3 — 3.0, learning

The removable tier: v3 code lives in `edgar.learning`, `edgar.controller` and
`providers/escalation.py`, and nothing in Core, v1 or v2 imports it. From M12
on, CI also deletes the removable packages and runs the suite below them
[NFR-12]. Budget **≤ 12,000 lines of code**. Each milestone ends with its tour
page (`docs/tour/learning.html`, `controller.html`, `synthesis.html`,
`escalation.html`), whose planned stops already exist in the Core tour's Part
III.

## M12 — Learning foundations

**Goal:** the harness learns from what you type and what breaks, safely.

- `learning/experience.py` — telemetry as a bus subscriber, including verification
  result, skills loaded and task shape [MEM-18]; `edgar stats` [MEM-19]
- `learning/learner.py` — autolearn from typed text only [MEM-8, MEM-9]
- `learning/error_facts.py` — templated facts from `ErrorRecord`s [MEM-22]
- `learning/history.py` — `history.md`, condensing, rotation,
  `history show|distill` (pending only) [MEM-12..14, MEM-16, MEM-17]. The
  out-of-band **model call** to condense was cut; `condense()` keeps the first 40
  words and the verbatim prompt stays in `learning.db` (ADR-0063)
- Property test: no generated trajectory produces an active fact whose provenance
  is not `user`, `user-prompt`, `user-feedback` or `error-template`

- **Tour delivery:** `docs/tour/learning.html`, turning the planned stop **s31**
  into a link (s25 in the original text; the stop was renumbered by M18); `just map`

**Done when:** a typed correction in session 1 changes behaviour in session 4 with
no `/remember`; a fetched page saying "remember X" never produces an active fact;
the suite is green with `learning/` deleted [NFR-12].

**Resolves:** OQ-1 — **gitignored by default**, with a documented opt-in.
`.edgar/history.md`, `.edgar/history.1.md` and `.edgar/learning.db` are in
`templates/gitignore.fragment`, so `edgar init` ignores them (ADR-0063).

**Built 2026-09-17** at 407 lines of code in `learning/`, plus 42 outside it for
the events, the CLI dispatch and the `--no-history` flag. `just loc` reads
9,766 of 12,000 for v3, and 9,359 of 9,500 for `src/` without the removable
packages — the binding number, leaving 141 lines of code outside v3's own
folders for all of M13, M14 and M15.

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

- **Tour delivery:** `docs/tour/controller.html`, s32 turned into a link; `just map`

**Done when:** every whitelist action is exercised with fabricated proposals, a
proposal attempting to loosen policy or naming an arbitrary model is rejected and
logged, no controller path can write `AGENTS.md` or a fact, and the suite is
green with `controller/` deleted [NFR-12].

**Built 2026-09-18** at 745 lines of code in `controller/`, plus 47 outside it
for the `[controller]` config section, the two `importlib` seams and the two
overrides in `cli/setup.py`, `ControllerActed`, the renderer's notice and the CLI
dispatch. `just loc` reads 10,558 of 12,000 for v3, and 9,406 of 9,500 for `src/`
without the removable packages — the binding number, leaving **94 lines of code**
outside v3's own folders for all of M14 and M15. `core/loop.py` is untouched at
200 of 200 and does not know the controller exists.

All four "done when" criteria hold, the fourth by hand: with
`src/edgar/controller/` deleted and its own six test files excluded, the suite is
917 passed and 11 failed, every failure being a tour or map test naming a file
that is gone. Four decisions a reasonable person could make differently are in
[ADR-0064](adr/0064-m13-controller-as-built.md), including two deviations from
[ADR-0008](adr/0008-controller-guardrails.md): the `learn` action is gone
(ADR-0017 removed it), and `propose_instruction` writes a Markdown note rather
than a unified diff against a file this code refuses to name.

Left for later, deliberately: `propose_skill` writes a proposal and stops until
M14 owns `skills.synthesis`, and `switch_model`'s targets are the configured
models until M15 adds the escalation chain [ROUTE-8].

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
- ~~`learning/curator.py` and `skills curate`, off by default [SKL-15]~~ *(Should; **cut** for budget, ADR-0065 §8)*

- **Tour delivery:** `docs/tour/synthesis.html`, s33 turned into a link; `just map`

**Done when:** J8 holds with the fake provider; a test asserts no tool output and
no error text reaches the synthesiser; in `auto` mode a property test over
generated trajectories shows no hand-authored skill file ever changes.

**Resolves:** OQ-6 (task shape definition).

---

## M15 — Escalation and route suggest

**Goal:** a weak model that fails gets help, visibly and within limits.

- `providers/escalation.py` — upward only, capped, announced [ROUTE-5, ROUTE-10]
- Reasoning off after a family switch [PRV-13]
- ~~Budget-aware downgrade before abort [ROUTE-11]~~ *(Should; **deferred** for budget, ADR-0066 §5)*
- ~~`edgar route suggest` over experience telemetry, print-only [ROUTE-12]~~ *(Should; **deferred** for budget, ADR-0066 §6)*
- ~~Responses API adapter if the eval set shows the gap (OQ-8)~~ *(resolved as "not yet"; no eval evidence, ADR-0066 §7)*

- **Tour delivery:** stop 34 in `docs/tour/index.html` turned into a link; no
  dedicated page for one file (ADR-0066 §8); `just map`

**Done when:** an escalation is visible in the status bar when a weak model fails
twice, never moves down the chain, and never exceeds `max_escalations`.

**Resolves:** OQ-8 — resolved as "not yet built"; revisit once an eval set shows
tool-heavy tasks losing to the missing adapter (ADR-0066 §7).

**Built 2026-09-23** at 90 lines of code in `providers/escalation.py`, plus
`Runtime.escalation` and the `_Escalator` protocol and its hook in
`core/loop.py`, `Escalation` in `core/events.py`, the `_escalation()` seam in
`cli/setup.py`, and the `Fallback`/`Escalation` notices in `cli/render.py` and
`cli/statusbar.py` (the latter closing a pre-existing ROUTE-10 gap for
`Fallback`, found while adding `Escalation`). `just loc` reads
11,064 of 12,000 for v3, and 9,396 of 9,500 for `src/` without the removable
packages — the binding number, leaving **104 lines of code** for the rest of
Core, v1 and v2. `core/loop.py` is at 196 of 200, four lines of slack, freed by
converting its module docstring to `#` comments. Four decisions a reasonable
person could make differently, including the two Should-item deferrals and the
OQ-8 resolution, are in [ADR-0066](adr/0066-m15-escalation-as-built.md).

All three "done when" observations hold: `tests/integration/test_loop.py`
scripts a weak model failing two consecutive rounds, asserts exactly one
`Escalation` event and the correct `from_model`/`to_model`, and a second test
asserts a zero-length chain with `max_escalations = 0` never escalates no
matter how many rounds fail; `tests/unit/test_cli_output.py` asserts the
status line's model updates on both `Fallback` and `Escalation`, not just that
an event fires.

---

# v4 — 4.0, unattended

The second removable tier: `edgar.broker` and `edgar.schedule`, attached
through the `pre_tool` veto stage and the host scheduler, never imported by
anything below them [NFR-12]. Budget **≤ 13,000 lines of code**. Order: M17
then M16, which carries the release ([ADR-0039](adr/0039-capability-broker.md)).
Each ends with its tour page (`docs/tour/broker.html`, `schedule.html`).

## M17 — Capability broker

**Goal:** every tool call answers to what the human asked for, and the record of
what was allowed and refused is signed. [ADR-0039](adr/0039-capability-broker.md).
Built after M15 and before M16, which carries the release.

- Intents recorded from typed text only: a REPL line (typed or queued) and the
  `-p` argument [CAP-1]
- `broker/caveats.py`, `broker/ticket.py`: the five caveats, attenuation, chain
  verification [CAP-2, CAP-5]
- `broker/authorize.py`: pure, property-tested [CAP-9]
- The veto in the `pre_tool` stage from M10, for every tool source; `shell` refused
  under a `paths` or `hosts` scope unless named; `ScopeRefused` [CAP-3, CAP-6]
- `--scope` and `/scope` [CAP-4]
- `task` attenuates the parent's ticket; `tighten_policy` adds caveats [CAP-5]
- `broker/receipt.py`: hash-chained, HMAC-signed, rebuilt on `--resume`;
  `~/.edgar/receipt.key` as a hard-layer credential path [CAP-7]
- `edgar receipt [ID] [--refused] [--verify]`; `[broker] enabled`; `doctor` line
  [CAP-8, CAP-10]

- **Tour delivery:** `docs/tour/broker.html`, s29 turned into a link; `just map`

**Done when:** the confused-deputy test passes on the fake provider: a session
scoped with `paths=reports/q3.md` asks for a summary; the file's text tells the
agent to read `reports/2024-salaries.md` and fetch an outside host; both calls are
refused, the model sees which caveat refused them, and `edgar receipt --refused`
shows both under the typed request. `--verify` passes on that receipt and exits 1
after a one-byte edit. A subagent cannot drop a caveat; a property test finds no
chain that verifies without one. With `broker/` deleted the suite is green [NFR-12].

---

## M16 — Scheduling · **v4.0 release**

**Goal:** unattended runs that cannot run away.

- `schedule/parser.py`, `schedule/due.py` — pure [SCH-4, SCH-5]
- `schedule/tick.py` — overlap prevention, catch-up policy [SCH-6, SCH-7]
- `schedule/install.py` — cron, launchd, Task Scheduler [SCH-3]
- `schedules.toml`, `edgar schedule add` appending from a template [SCH-1, SCH-12]
- Per-entry mode, agent, model, allowlist, verify [SCH-8]
- Run transcripts, `session_end` hook [SCH-9, SCH-10]
- `schedule_self` in the `self_schedules` table, with guardrails [SCH-11]
- Broker tickets for scheduled runs: an entry's `scope` and allowlist as caveats,
  actor `schedule:NAME`; a `schedule_self` row stores its creator's ticket,
  attenuated [CAP-1, CAP-4, CAP-5]
- Notifications as a `session_end` hook: an example hook in `examples/hooks/`
  posting the run's summary to a webhook or the desktop notifier, 0 lines of
  `src/`; moved here from the deferred list because an unattended run that
  cannot tell anyone it finished is not unattended, it is lost
- **Tour delivery:** `docs/tour/schedule.html`; `just map`

**Done when:** frozen-clock tests cover every catch-up policy, overlap is
prevented, a self-schedule never touches `schedules.toml` or holds more authority
than the run that created it, and the v4.0 success
criteria in PRD §11 are met with `src/` under 13,000 lines of code.

---

## Past v4

Ordered by expected value, not commitment.

1. **Concurrent read-only tool calls within one response** — calls run in order
   today (TOOL-12); revisit with ordering guarantees if latency demands it
2. **OpenAPI import** — generate HTTP tools from a spec
3. **Vector or graph retriever plugins** — through the retriever port, if one beats
   multi-term FTS on the eval set (ADR-0024)
4. **TUI mode** — behind a flag, never replacing line-oriented output
5. **Shared or remote memory** — team-level facts
6. **Language-server tools** — `shell` and command tools cover the common cases
7. **Homebrew and Scoop manifests** — when someone asks
8. **Prompt-caching optimisation** across providers, not just Anthropic
9. **The `container` sandbox backend** — M21 had room (277 of ~350) but did not
   build it speculatively; the `wrap` port (ADR-0061) is the shape it would use

10. **A user manual** — one short doc covering every slash command, tool, skill,
    how to install and upgrade the CLI and MCP servers, and edgar's
    idiosyncrasies a user must know, so a new user is not left reading source.
    Requested 2026-09-17.
11. **`/help` (`/h`) lists everything** — today it is not built; when it is, it
    must print every slash command, tool and skill with a one-line description
    each, formatted for a terminal (one line per entry). Requested 2026-09-17.

Images moved into M20 ([ADR-0052](adr/0052-media-input-in-v2.md),
[ADR-0057](adr/0057-daily-driver-before-learning.md)); web search and git tools
into M20 as extensions; notifications into M16.

## Never

Listed so the question stops recurring. Full rationale in PRD §5.2.

MCP server mode · server/daemon/HTTP API · RAG or vector index · multi-user or RBAC
· GUI · fine-tuning · plugin marketplace or skill hub (extensions are copied, never
installed from an index) · messaging gateway · user modelling · memory nudges in
the prompt · agent-to-agent network protocols · racing to support fifty providers
