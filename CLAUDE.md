# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read AGENTS.md first

[`AGENTS.md`](AGENTS.md) is the authoritative instruction file for agents working here.
It carries the non-negotiable constraints, code conventions, architecture rules, size
budgets and commit format. This file is orientation only and must not contradict it.
`AGENTS.md` is hand-authored and no automated process may modify it (ADR-0007, ADR-0008);
the same applies to `config.toml`. If you think it needs a change, propose the diff to
the maintainer instead of editing it.

The spec was revised to v0.3 and v0.4 on 2026-09-13 ([`docs/DECISIONS.md`](docs/DECISIONS.md),
ADRs 0015–0025; v0.4 is grounded in [`docs/research/hn-2026-09.md`](docs/research/hn-2026-09.md)).
If `AGENTS.md` still lists `pydantic` in the startup import ban, "three autolearn
sources" as the memory rule, or has no rule about hidden behaviour or ports, the
maintainer has not yet applied the matching hand edits: follow the ADRs and mention
the mismatch.

The positioning every change should serve: **"the agent harness you can read in an
afternoon. Any model. No hidden calls. Nothing is done until it's verified."**

## Current state

All five tiers are built and released (https://github.com/vespassassina/edgar):
Core and v1 as 0.1.0 and 1.0.0, then on 2026-09-24 **2.0.0** (v2, the daily
driver, M18–M22), **3.0.0** (v3, learning, M12–M15) and **4.0.0** (v4,
unattended: M17 the capability broker, M16 scheduling). Each is on PyPI
(`uvx edgar-harness`), `ghcr.io` and as GitHub release binaries for all three
platforms. 2.0 and 3.0 were cut on `release/2.0` and `release/3.0`, where their
tier was whole; `main` carries 4.x. The "as built" ADRs are 0054–0066; the
roadmap's status table has what each milestone deferred.

The budget is nearly spent where it matters: `just loc` reads 12,191 of the
v4 budget of 13,000, but **9,497 of 9,500 outside the removable packages**.
Anything that touches Core, v1 or v2 code must free lines first (narration to
`#` comments is free under ADR-0040) or move to a later tier. Read the latest
entry of `docs/JOURNAL.md` and its pending list before starting; there is no
`docs/HANDOFF.md` unless a session stopped mid-task.

**A fifth line, Olivia, is specified but has no code yet**: ADR-0067 forks a
governable, fully autonomous agent onto a long-lived `olivia` branch (cut from
`main` on 2026-09-24), with amended rules on that line only; ADR-0068 records
the design interview (governor, Jev's two Decider interfaces, memory and
observability plugins, the home-routine learning amendment, a 20,000 LOC
budget). On the `olivia` branch, ADR-0069 (Proposed) is the tier ADR: layout,
the governor's place after the permission engine, the four seams into
`src/edgar/`, the budget per milestone and milestones O0–O7. The spec is
`docs/olivia/PRD.md`, the plan `docs/olivia/ROADMAP.md`, the workloads
`docs/olivia/use-cases.md`. O0 waits on ADR-0069's acceptance and the
maintainer's hand edit of `AGENTS.md` on that branch.

Releases go out through trusted publishing when a `v*` GitHub release is
published: bump the version in `pyproject.toml` and `src/edgar/__init__.py`,
run `uv lock`, move CHANGELOG's "Unreleased" under the version, and check CI on
`main` is green on all three platforms first (it was red on Windows for a day
unnoticed before 4.0).

Tests drive the loop through `tests/support/harness.py` (`scripted()`, `runtime()`,
`Recorder`, `SlowTool`); assert on `recorder.names` for event sequences. REPL tests
drive `Shell` directly (`tests/integration/test_repl.py`); long-session tests use a
small-window provider in `tests/integration/test_sessions.py`. Provider tests drive
adapters through the `rig` fixture (`tests/support/rig.py`), which replays
`tests/cassettes/<provider>.json`; every cassette entry is still `synthetic` until
someone with keys runs `just record-cassettes NAME`. The `eval` recipe arrives
with the milestone that creates evals.

Docs are still most of the product, so treat an edit to `docs/` with the same care as
code. Ruff is configured to skip `*.md`: the Python blocks in the docs are hand-aligned
and must not be reformatted.

## Commands

Python 3.12+, `uv`-first, `just` as the task runner (ADR-0001).

```bash
just check      # ruff format + ruff check + mypy --strict + offline tests. Run before every commit.
just test       # offline suite: unit, property, contract-vs-cassettes, integration, e2e
just cov        # coverage report
just fmt        # ruff format + safe lint fixes
just loc        # size against the tier budget (tests/support/budget.py)
```

Narrower suites, and the ones that cost money:

```bash
just test-unit
just test-property
just test-contract
just test-live            # hits real providers, needs API keys
just record-cassettes openai   # re-record one provider's HTTP fixtures
just eval                 # outcome-scored tasks, slow and non-blocking
```

A single test is plain pytest, for example
`uv run pytest tests/property/test_compaction.py::test_elide_keeps_the_pairing_and_is_idempotent -x`.

The offline suite must stay under 60 s (NFR-2) and applies the `no_network` fixture
suite-wide, so any accidental socket call fails loudly rather than passing slowly.

## Writing code here

The maintainer's standing rules, recorded in ADR-0040 and PRD §4; `AGENTS.md` carries
the same rules.

- **Lines means lines of code.** Every size limit counts non-blank lines that are
  not only a comment. Docstrings count; comments are free. Say "lines of code" in
  docs whenever a limit is stated.
- **Pseudocode comments in every file you touch.** A file with a flow opens with
  that flow as a pseudocode comment block; long functions number their steps
  (`# 1. …`). Narrate in `#` comments, not docstrings. `core/loop.py`,
  `core/message.py` and `core/events.py` show the style.
- **Shallow functions, no recursion where a loop works.** A top-level function reads
  as a list of steps; each step with detail is a helper one level down; helpers do
  not call each other. Shared state goes in a small mutable dataclass (`_Turn` in
  `core/loop.py`).
- **Sensible defaults.** Every prompt or setup question offers a pre-selected
  answer that is right most of the time, so Enter is usually enough. Installing,
  `init` and deploying leave working, commented config files, never blanks. A
  default is shown and never picks a model or host the user did not configure.
- **Keep the tour in sync.** [A Tour of the Harness](https://vespassassina.github.io/edgar/)
  (source: `docs/tour/index.html`) changes in the same commit
  as the code it describes. `tests/unit/test_tour.py` catches broken references,
  not stale prose, so reread the stop for any file you change. A milestone that
  adds a module turns its planned stop into a built one.

## Architecture in one pass

`docs/BLUEPRINT.md` has the full module map, data model and interfaces. The shape worth
holding in your head:

**Five tiers with a hard seam.** Core (M0–M6, ≤ 5,000 LOC) is the smallest honest
harness; v1 (M7–M11, ≤ 8,000) adds memory, MCP, subagents, extensions and freezes the
extension formats; v2, the daily driver (M18–M22, ≤ 9,500), adds tours for v1 and a
map, `@path`, plan mode and `todo`, images, web search and git as extensions,
worktrees and sandboxes, and the inspection commands, all inside Core and v1
packages, so it is not removable; v3, learning (M12–M15, ≤ 12,000), adds learning,
the controller, synthesis and escalation; v4, unattended (M17 then M16, ≤ 13,000),
adds the capability broker and scheduling. v3 and v4 live in `edgar.learning`,
`edgar.controller`, `edgar.schedule`, `edgar.broker` and `providers/escalation.py`,
and nothing in Core, v1 or v2 may import them: they attach through the loop's
post-turn gate and the tool pipeline's `pre_tool` vetoes (both filled by name with
`importlib`) and the event bus (ADR-0015, ADR-0057, NFR-12). PRD §5.1 maps every
requirement ID to its tier.

**One loop.** `core/loop.py` is under 200 lines of code and pushes every concern into a
collaborator: context assembly, provider resolution, tool execution, the verify gate.
Tool calls from one response run in order; consecutive `task` calls fan out
concurrently (TOOL-12). A subagent is not a second engine, the `task` tool re-enters the
same loop with a different config, a fresh transcript and a narrowed policy (ADR-0006).

**One message vocabulary.** `core/message.py` defines frozen, slotted `Message` and
content blocks. Nothing outside `providers/` ever sees a provider-native structure.
Immutability is what makes compaction idempotent and property testing straightforward.

**Providers translate, they do not decide.** Four OpenAI-compatible providers (OpenAI,
Azure, OpenRouter, Ollama) and any user-declared compatible server share
`openai_compat.py` driven by a data table in `quirks.py`; Anthropic has its own adapter.
Differences are data, never branches in the loop (ADR-0002, ADR-0020). Everything
resolves lazily through `providers/registry.py`. `ThinkingBlock` carries its `origin`;
foreign reasoning is dropped on serialisation, never rewritten.

**Ports and adapters, one distribution.** The core (`core/`, `context/`,
`permissions/`, `tools/execute.py`) imports no adapter; a test enforces it.
Provider, Tool source, Skill source, Sandbox, Retriever and Output are ports with
built-in adapters; third-party Provider, Sandbox and Retriever adapters register
through entry points. Session storage and the permission engine are deliberately
not ports (ADR-0022).

**No hidden behaviour.** No model, host or telemetry the user did not configure;
auxiliary roles default to the main model. The system prompt is
`prompts/system.md` (≤ 1,500 tokens, no style opinions). Nothing above the cache
breakpoint changes within a session, so never put a date or anything volatile
there; it goes in the current turn (ADR-0023, CTX-17).

**Extensions are files.** Tools come in four kinds: built-in, command (argv template,
never a shell), HTTP (request template, host fixed, secrets from env only) and MCP
(stdio and Streamable HTTP). Skills, agents, hooks (observe or veto, never allow) and
extension folders bundling them complete the vocabulary. Python is a plugin surface
only for providers (ADR-0018).

**Output goes through the event bus, never through print.** The loop and tools emit
events; the status bar (stderr), renderer (stdout), telemetry and logger subscribe. That
decoupling is what lets the same loop serve interactive, piped, subagent and scheduled
execution (ADR-0011).

**Pure functions carry the correctness.** `permissions.decide()`, `routing.select_model()`,
`schedule.compute_due()`, `context.compact()` and token counting are pure by design so
they can be property-tested exhaustively. If one of them needs I/O, pass the result in.

**Three model mechanisms, kept apart.** Routing decides up front as a pure function over
declarative rules; escalation goes upward on capability failure and is capped and
announced; fallback goes sideways on provider unreachability and never reduces
capabilities. They are conflated constantly elsewhere and must not be merged here
(ADR-0013).

**Context is compressed in stages, on whole units.** S0 spills large tool output to
`sessions/<id>/blobs/`, S1 elides old tool results to stubs with no model call, S2
folds old turns into one rolling summary, S3 raises `ContextOverflow` if the pinned
content alone does not fit. Compaction runs from `compact_at` (0.70) down to
`compact_to` (0.50). The prompt is compressed; the JSONL record never is (ADR-0016).
The plan and todo list (v1, ADR-0037) are pinned working state just above the
current turn and survive compaction (ADR-0025).

**Memory has a security boundary.** An active fact comes only from text a human typed
or from an `ErrorRecord` the harness computed; everything else (the model's `remember`
calls, `history distill`) creates pending facts that are never injected until a human
confirms. Nothing on the learning path reads tool output, error text, fetched content,
piped stdin or `@file` attachments. It is enforced by what each function accepts, not
by filtering (MEM-8, MEM-9, ADR-0017). The pinned fact set is frozen at session start
so the prompt-cache prefix stays stable (MEM-6). Recall is lexical (FTS5, porter +
trigram, multi-term queries); no embedding model in core, vectors or graphs only as
Retriever plugins (ADR-0024).

**Done means verified.** `core/verify.py` runs a declared check when the model stops
calling tools, only after turns that ran a non-read tool. Failure output goes back to
the model, capped attempts, exit 9 when exhausted (§7.14, ADR-0014).

**Skills are learned from verified work only (v3).** Synthesis triggers are
deterministic checks in the controller's post-turn gate. The synthesiser sees the
outline of a run (typed prompt, corrections, tool calls in order, `ErrorRecord`s,
verify result), never tool output or error text.
`skills.synthesis` is `propose` by default; `auto` writes only into the machine-owned
`.edgar/skills/learned/`, only after a passing check, and prints a disclaimer every
session (SKL-8..16).

## Invariants that break things silently

These cost the most when violated:

1. **Compaction pairing.** Every assistant message with tool calls is immediately
   followed by exactly one tool message whose result ids equal the call ids. Every
   provider returns 400 if you break it. Compaction only removes, stubs or summarises
   whole units (a call message plus its result message), so the invariant holds by
   construction; never trim inside a unit (CTX-4, ADR-0016). The same rule places a
   `/steer`: it lands only at the loop's one safe point, between units, and a `/btw`
   snapshot is cut back to the last complete unit (ADR-0028).
2. **Humans widen, machines tighten.** No automated component (model, tool, subagent,
   controller, learner, hook) may widen policy. Control files are Ask for `write` and
   `edit` in every mode but `yolo`; config is read once per session; grants live in the
   DB, never in config; tainted `auto` sessions tighten shell and network defaults;
   executable project config needs `edgar trust` (PERM-6, PERM-8, PERM-11..13,
   ADR-0021).
3. **Startup budget.** `import edgar.cli.main` must pull in no `httpx`, `rich`,
   `prompt_toolkit`, `jsonschema`, `yaml`, `keyring` or `edgar.providers.*`. Heavy
   imports live inside functions with a comment naming the reason. The budget is
   ≤ 150 ms to first output byte for a trivial `-p` run, and a CI test enforces it with
   `-X importtime` (NFR-1, ADR-0012, ADR-0019).
4. **Tool failures return to the model.** Validation errors, hook vetoes, denials and
   timeouts all become `ToolResultBlock(is_error=True)` with a harness-computed
   `ErrorRecord`; only unrecoverable loop failures raise.
5. **The learning boundary.** Only typed text and `ErrorRecord`s create active facts;
   the synthesiser never sees tool output or error text; `auto` synthesis never fires
   without a passing verification, and writes only into `learned/`. Machine-writable
   locations are listed in PRD §9.5; everything else is hand-authored (ADR-0014,
   ADR-0017).
6. **Tier isolation.** Core, v1 and v2 code never imports the v3 and v4 packages; CI
   deletes them and runs the suite below them (NFR-12).
7. **Byte-stable prefix and no implicit hosts.** A `datetime.now()` in the prompt
   builder or a helpful default model for an auxiliary role silently breaks the
   prompt cache or sends prompts somewhere the user never chose. Both have tests
   (CTX-17, PRV-15).

Requirement IDs in brackets trace to `docs/PRD.md`. Cite them in commits and tests.

## Working on a milestone

Roadmap order (ADR-0033 moved M4 ahead of M3; IDs keep their numbers): **Core** M0
skeleton, M1 loop with the fake provider and config loading, M2 real providers, M4
REPL, streams and the model picker, M3 tools, permissions, the verify gate, command
and HTTP tools and project trust, M5 context and sessions, M6 skills, `edgar login`
and the Core release. **v1** M7 memory
and session search, M8 MCP, M9 subagents, routing rules and fallback, M10 extensions,
hooks, plugins and `edgar.run()`, M11 init, doctor and docs (1.0). **v2, the daily
driver** (ADR-0057) M18 tours for v1 and the map (no `src/` code), M19 working state,
M20 seeing and searching, M21 isolation, M22 inspection and the 2.0 release. **v3,
learning** M12 learning foundations, M13 controller, M14 skill synthesis, M15
escalation and route suggest (3.0). **v4, unattended** M17 capability broker
(ADR-0039, built before M16), M16 scheduling (4.0). Each milestone's last item is
its tour page or stops; a milestone with code and no tour is not done. Each ships something tested and documented; docs are updated in
the same commit, never later. If a milestone pushes its tier over the LOC budget,
something moves to a later tier; the budget does not move.

The fake provider in M1 is the leverage for everything after it. Any test that does not
specifically exercise provider translation should use it. A new provider is done when the
parametrised contract suite passes for it, not when it works once by hand.

Before building anything, check the "Never" list at the end of `ROADMAP.md` and the
non-goals in `PRD.md` §5.2. Skill hub, messaging gateway, user modelling and memory
nudges are on it deliberately. If the spec is wrong, say so and change the doc and the code
together rather than deviating quietly.

## Keeping track

The maintainer's standing rule: everything we do leaves a written trace in the
repo, in the same commit as the work.

- `docs/JOURNAL.md`: a dated entry per session with what was asked, done, decided
  and still pending. Requests not acted on yet go in its pending list.
- `CHANGELOG.md`: user-visible changes under "Unreleased"; moved under a version
  on release.
- `docs/ROADMAP.md`: the status table at the top.
- `docs/adr/`: an ADR for any decision a reasonable person could make differently.

## Environment notes

`.venv` is a symlink to `.venv.nosync`, which iCloud Drive does not sync; if `uv sync`
ever replaces the symlink with a real directory, recreate it. The working copy lives
in `~/Documents`, which iCloud Drive syncs (an older identical
copy sits in OneDrive at `~/onedrive/Projects/edgar`; do not edit both). SQLite in a
cloud-synced directory is a known hazard (WAL mode, short transactions, busy timeout),
so expect it to surface once `storage/db.py` exists in M3. `edgar doctor` warns for
iCloud Drive, OneDrive, Dropbox and Google Drive folders (CFG-5).

Windows is a first-class target from M0 and no platform skips are permitted in core
tests. If something cannot run on Windows, the code is wrong, not the test (NFR-6).

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.
