# Decisions — spec revisions v0.3, v0.4 and v0.5

What changed in the spec on 2026-09-13 (v0.3, v0.4) and 2026-09-16 (v0.5), and why. This page is the readable summary;
the ADRs are the formal record. [v0.4](#revision-v04--the-field-review) follows a
field review of 11,647 Hacker News comments; v0.3, below it, came out of a full
review of v0.2 against the project's goal:

> **A lightweight, extensible, open and easy-to-use agentic harness for the terminal,
> small enough to read in an afternoon.**

The review found that the design reasoning was strong and the scope was not
lightweight: 154 Must requirements inside 8,000 lines and eight dependencies. It
also found five leaks in the memory security claim, four side doors around
"policy may only tighten", a compaction invariant weaker than what providers
enforce, and a dozen places where the documents disagreed with each other.

---

## Revision v0.5 — the daily driver first (2026-09-16)

v1.0 went code-complete at exactly 8,000 of 8,000 lines of code without anyone
having worked a day in it. ADR-0015's next tier was learning, which learns from
use there has not been. [ADR-0057](adr/0057-daily-driver-before-learning.md)
puts a new tier in front of it and splits the old v2 in two:

| Tier | Milestones | Promise | Budget |
|---|---|---|---|
| v2, the daily driver | M18–M22 | Tours for v1 and a map; `@path`, plan mode and `todo`; images, web search and git; worktrees and sandboxes; the inspection commands cut by ADR-0053. Extends Core and v1, not removable | ≤ 9,500 LOC |
| v3, learning | M12–M15 | Learning, controller, synthesis, escalation. Removable | ≤ 12,000 LOC |
| v4, unattended | M17, M16 | Broker, scheduling, notifications. Removable | ≤ 13,000 LOC |

What holds from before: milestone IDs keep their numbers, budgets are
constraints not estimates, NFR-12's removability rule (now naming v3 and v4),
semver's meaning. What is new: every milestone's last item is its tour, and
2.0's done test is two weeks of real use plus PRD §11's two human checks by an
outside person, not a checklist. Web search and git cost zero lines of `src/`:
they are extensions in `examples/`, which is what EXT-10's freeze was for.

---

## Revision v0.4 — the field review

Forty Hacker News threads about Claude Code, OpenCode, Codex CLI, Gemini CLI,
Aider, Pi, Crush, Letta Code, AGENTS.md, skills, MCP, agent memory and sandboxing
were read in ranked order, 11,647 comments in all. The evidence, method and
caveats are in [research/hn-2026-09.md](research/hn-2026-09.md).

**What people are angry about:** harnesses that do things nobody configured
(prompts sent to a hosted model for titles, remote config, hidden prompt changes),
bloated and fast-churning codebases, token waste, vendor lock-in, weak security
posture, and TUIs that fight the terminal.
**What they need:** plans and todo lists that survive compaction, context control
(forks, elided output), isolation that is not theatre, small models that work, and
memory that is small and editable.
**What they praise:** minimal harnesses, open model-agnostic ones, tests as
feedback.

### The headline

> **edgar — the agent harness you can read in an afternoon.**
> Any model. No hidden calls. Nothing is done until it's verified.

Each clause answers something the review found missing elsewhere: *read in an
afternoon* answers bloat (per-tier size budgets); *any model* answers lock-in (API
keys and any compatible endpoint); *no hidden calls* answers the loudest complaint
(ADR-0023); *nothing is done until it's verified* answers agents that claim success
(the verify gate runs the check itself).

### Would internal embeddings or a graph make a better memory?

No, not in core. [ADR-0024](adr/0024-lexical-memory.md)

- Coding agents search for exact strings: error messages, function names, flags.
  Lexical search finds those; semantic search blurs them
- The leading harnesses use grep, and models are trained so heavily on it that
  they distrust other search results
- Auto-extracted, similarity-consolidated memories degrade in practice; users of
  such systems report databases full of wrong facts, and similarity cannot tell
  when two facts contradict
- An embedding model is hundreds of megabytes or a network call, and its results
  are nondeterministic: it breaks the size budget, "no hidden calls" and the
  property tests at once
- The "graph" people liked in the review (Beads) is a dependency graph of tasks,
  which is explicit structure, not inferred semantics

What edgar does instead: FTS5 with a word index and a trigram index; a `recall`
tool that takes several terms so the model supplies the synonyms; explicit links
between facts (`supersedes`, scopes, tags). And a **retriever port**, so anyone who
wants vectors or a graph can plug one in as a package without touching core.

### Should adapters, tools and skills be split out of the harness?

Split the **interfaces**, not the **distribution**. [ADR-0022](adr/0022-ports-and-adapters.md)

The core (loop, messages, events, context, permissions, the tool pipeline) imports
no adapter, and a test enforces it. Everything else plugs in through a port, each
with built-in adapters and room for more:

| Port | Built-in | Add your own |
|---|---|---|
| Provider | OpenAI-compatible, Anthropic, fake | a config block, or a package |
| Tool source | built-in, command, HTTP, MCP | a TOML file, or an MCP server |
| Skill source | `SKILL.md` folders | files |
| Sandbox | none, bubblewrap, Seatbelt, container | a package |
| Retriever | FTS5 | a package |
| Output | terminal, `--json`, `--events` | `edgar.run()` subscribers |

It all ships as **one distribution**. Separate packages per adapter would mean a
version matrix, more to install, a reader jumping between repositories, and more
publishing pipelines to secure: LiteLLM's PyPI releases were compromised through
its CI in 2026. Because the layering is enforced, a later split (for example an
`edgar-core` for people who embed only the loop) is a packaging change, not a
refactor.

Session storage and the permission engine are deliberately not ports.

---

## The short version (v0.3)

1. **Three tiers.** Core (0.x) is the smallest honest harness. v1.0 makes it
   extensible and gives it memory, and freezes the extension formats. v2.0 adds
   learning and unattended runs. v2 is removable. [ADR-0015]
2. **Context is compressed in four stages, cheapest first:** spill big outputs to
   disk, elide old tool results, summarise old turns, and fail loudly if the pinned
   content alone does not fit. Everything operates on whole units, so the pairing
   invariant holds by construction. [ADR-0016]
3. **Only text a human typed, or an error the harness classified itself, creates an
   active fact.** Everything else is pending until a human says yes. [ADR-0017]
4. **One extension vocabulary:** tools (built-in, command, HTTP, MCP), skills,
   agents, hooks, and extensions that bundle them. Files first, MCP for code,
   Python only for providers. [ADR-0018]
5. **Five required dependencies.** `pydantic`, `tomli-w`, `platformdirs` dropped;
   `keyring` optional; `PyYAML` added because frontmatter is YAML. [ADR-0019]
6. **Any OpenAI-compatible server is a config block.** Reasoning blocks are tagged
   with their origin and dropped when a session switches provider family. [ADR-0020]
7. **Humans widen, machines tighten.** Control files are always-ask, grants live in
   the DB, `auto` mode tightens after untrusted content arrives, and cloned
   projects need trust before their hooks and tools run. [ADR-0021]

---

## Answers to the questions behind this revision

### Should there be Core, v1 and v2?

Yes. The tiers exist because the budget and the feature list could not both hold,
and the spec had no rule for which one gives way. Now it does.

| Tier | Promise | Budget |
|---|---|---|
| **Core** (0.x) | Read it in an afternoon, use it every day. Five providers plus any OpenAI-compatible server, built-in tools, command and HTTP tools, skills, permissions, verify gate, staged compaction, sessions and resume, `-p`, `--json`, `--events`, REPL | ≤ 5,000 LOC |
| **v1.0** | Extensible and remembers. Facts memory, session search, MCP, subagents, routing rules and fallback, extensions and hooks, provider plugins, `edgar.run()`, `init` and `doctor`. **Extension formats frozen** | ≤ 8,000 LOC |
| **v2.0** | Learns and runs unattended. Controller, autolearn, `history.md`, telemetry, skill synthesis, escalation, `route suggest`, scheduling | ≤ 11,000 LOC |

Core ships to PyPI as 0.x so people can use and fork it long before v2 exists. 1.0
is where compatibility promises start, which is what the second audience (people
building on edgar) needs. v2 lives in `edgar.controller`, `edgar.learning` and
`edgar.schedule`; nothing in Core or v1 imports them, and CI proves v1 works with
them deleted.

### How do memory, learning and context work?

Five layers, each with one owner:

| Layer | What it holds | Written by | Tier |
|---|---|---|---|
| **Instructions** | `AGENTS.md` (and any configured file such as `CLAUDE.md`) | the human only | Core |
| **Transcript** | the current session, compressed as needed | the loop | Core |
| **Record** | every session in full, as JSONL, searchable with FTS5 | the loop, append-only | Core (storage), v1 (search) |
| **Facts** | durable notes with scope, provenance and confidence, in SQLite, editable as markdown | the human; the model can only *propose* | v1 |
| **Learning** | autolearn, error facts, `history.md`, telemetry, skill synthesis | v2 components, under ADR-0017 | v2 |

**Getting facts into a prompt:** a bounded pinned set, chosen by scope,
confidence, use count and recency, computed at session start and frozen so the
prompt cache survives; plus a `recall` tool over FTS5 for everything else,
including past sessions. No embeddings: the reader can see exactly why a fact
surfaced.

**Learning, safely:** in v1, nothing is learned automatically. You say
`/remember we use pytest`, or the model calls `remember` and you confirm at the end
of the turn. In v2, autolearn reads only what you typed (never piped stdin, never
attached files, never tool output) and turns harness-classified errors into
templated facts such as "`python` was not found on PATH here (3 times)". Anything
else, including `history distill`, produces pending facts you review.

### Can we compress context?

Yes, in four stages, run only until the prompt is back under target [ADR-0016]:

| Stage | Cost | What it does |
|---|---|---|
| **S0 Spill** | free | Big tool outputs are head/tail truncated. The full text goes to `.edgar/sessions/<id>/blobs/`, and the marker tells the model where to `read` it |
| **S1 Elide** | free | Old tool results become one-line stubs (tool, arguments, size, blob path). Old thinking blocks are dropped |
| **S2 Summarise** | one cheap call | The oldest turns fold into one rolling summary: goal, decisions, files, open threads, errors, blobs worth re-reading |
| **S3 Overflow** | free | If even the pinned content does not fit, elide inside it; if still too big, stop with a clear error and a hint |

Compaction starts at 70% of the window and works down to 50%, so it does not run
on every request and wreck the prompt cache. It always removes or replaces whole
units (a tool call together with its results), so it can never produce a
transcript a provider rejects. **The prompt is compressed; the record never is.**
The JSONL keeps everything, and session search finds elided content again.

Subagents are the other big compression tool: a subagent explores in its own
context and returns a summary. Skills (description only until loaded) and `recall`
(facts on demand instead of pinned) keep the prompt small from the start.

### Tools, skills and extensions, with access to CLIs and APIs

| You want the agent to… | Use | Example |
|---|---|---|
| run any command | the `shell` tool, under permissions | `pytest -x` |
| use one CLI safely | a **command tool**: argv template, schema, no shell | `gh issue view {number}` |
| call one web API | an **HTTP tool**: request template, host fixed, secrets from env | `GET https://api.example.com/v1/forecast?lat={lat}` |
| use real code or state | an **MCP server**, any language | a database client |
| follow a procedure | a **skill** (`SKILL.md`, Claude-compatible) | "how we cut a release" |
| delegate with another model | an **agent** (markdown + frontmatter) | a cheap local explorer |
| react to what happens | a **hook**: observe, or veto a tool call | run a formatter after `edit` |
| share all of the above | an **extension** folder with `extension.toml` | `extensions/github/` |
| add a model provider | a config block, or a Python **provider plugin** | LM Studio, Gemini |

Other programs use edgar through `-p --json`, `-p --events` (the event stream as
JSON Lines) and `edgar.run()`. No daemon, no HTTP API.

---

## Every decision in v0.3

Each entry: what was decided, why, and what changed. IDs in brackets are PRD
requirements; they are listed so the change can be traced.

### D1 — Release tiers · [ADR-0015](adr/0015-release-tiers.md)

**Decision.** Core ≤ 5,000 LOC, v1 ≤ 8,000, v2 ≤ 11,000; `core/` ≤ 2,000 always.
v2 in its own packages, isolated by an import test and a delete-v2 CI job.
**Why.** The goal says lightweight. Tiers turn "lightweight" from an aspiration
into a rule about what moves when the budget is hit.
**Changed.** PRD §5.1 (tier map), NFR-4, new NFR-12, ROADMAP regrouped into
M0–M6 / M7–M11 / M12–M16, BLUEPRINT §2 package layout.

### D2 — Staged context compression and a stronger invariant · [ADR-0016](adr/0016-context-pipeline.md)

**Decision.** Spill, elide, summarise, overflow; whole units only; hysteresis
between `compact_at` and `compact_to`; compaction records appended to the JSONL.
**Why.** The old invariant accepted transcripts providers reject, had no answer
when pinned content was too big, and paid a model call to remove content the model
had already used.
**Changed.** CTX-1, CTX-3, CTX-4, CTX-5, TOOL-4; new CTX-11 to CTX-14; BLUEPRINT
§3.1, §8; TESTING pairing, idempotency, overflow and spill tests.

### D3 — The learning boundary · [ADR-0017](adr/0017-learning-boundary.md)

**Decision.** Active facts only from human-typed text or harness-computed error
records; everything else pending; the controller's `learn` action removed; the
synthesiser gets error records, not error text; stdin and `@file` attachments are
tagged and excluded.
**Why.** Five paths let tool output reach memory despite the "by construction"
claim: error text, controller `learn`, piped stdin, `history distill`, and the
model-called `remember` tool.
**Changed.** MEM-8, MEM-9, MEM-17, SKL-9, CTRL-4, CLI-3; new MEM-21 to MEM-23;
BLUEPRINT §10, §11.

### D4 — One extension vocabulary · [ADR-0018](adr/0018-extension-model.md)

**Decision.** Tools in four kinds (built-in, command, HTTP, MCP), skills, agents,
hooks, extensions; Python only for provider plugins; `--events` and `edgar.run()`
for embedding.
**Why.** "Access to CLIs and APIs" needed first-class, safe forms that are not the
raw shell, and integrations needed a unit to share.
**Changed.** TOOL-6, TOOL-9; new §7.15 EXT-1 to EXT-10, CLI-18, PRV-14; BLUEPRINT §6.

### D5 — MCP transports · [ADR-0018](adr/0018-extension-model.md)

**Decision.** stdio and Streamable HTTP. No legacy HTTP+SSE. Static headers from
env in v1, OAuth in v2. Server annotations never drive permissions.
**Why.** The MCP specification replaced HTTP+SSE with Streamable HTTP in its
2025-03-26 revision; building the old transport is building for the past.
**Changed.** TOOL-7.

### D6 — Dependencies · [ADR-0019](adr/0019-dependency-budget.md)

**Decision.** Required: `httpx`, `jsonschema`, `PyYAML`, `prompt_toolkit`, `rich`.
Optional: `keyring`. Dropped: `pydantic`, `tomli-w`, `platformdirs`.
**Why.** The list was already nine against a cap of eight once YAML and keyring
were counted, and `pydantic` sat on the startup path through config validation.
**Changed.** NFR-5, CFG-6, BLUEPRINT §16, startup import test.

### D7 — Provider portability · [ADR-0020](adr/0020-provider-portability.md)

**Decision.** User-defined OpenAI-compatible providers as config; `ThinkingBlock`
carries `origin`; foreign reasoning is dropped on serialisation; a mid-turn switch
of family disables reasoning for the rest of the turn; Chat Completions for the
compatible family, with a Responses API adapter as a sanctioned optional third.
**Why.** Openness (any compatible server) and a cross-family switch that the
v0.2 escalation example would have turned into a 400.
**Changed.** ROUTE-7; new PRV-12, PRV-13; BLUEPRINT §3.1, §5; OQ-8.

### D8 — Humans widen, machines tighten · [ADR-0021](adr/0021-humans-widen-machines-tighten.md)

**Decision.** Control files are Ask in every mode but `yolo` and read once per
session; grants and self-schedules live in the DB; `decide()` takes a `tainted`
input that tightens `auto` after network content arrives; project trust gates
executable project config; shell patterns match per segment and are documented as
a speed bump.
**Why.** The model could edit its own config, "always allow" wrote to a
hand-authored file, `auto` plus `fetch` plus `shell` is the exfiltration setup,
and a cloned repository could run hooks and tools on launch.
**Changed.** PERM-6, PERM-8, SCH-11, §9.5; new PERM-11 to PERM-14, CFG-8, CLI-19;
BLUEPRINT §7; TESTING property tests.

### D9 — Tool calls within one response

**Decision.** Calls from one model response run **in order**. Consecutive `task`
calls form a fan-out group and run concurrently, capped by `subagents.max_parallel`.
Permission prompts, including those from subagents, go through one queue and are
asked one at a time, labelled with the agent's name.
**Why.** The PRD deferred parallel tool execution, while the Blueprint's loop ran
every call in parallel and the Roadmap said calls "currently run together".
Sequential is deterministic, keeps prompts readable, and parallelism is kept where
it pays: subagents.
**Changed.** PRD §5.3, TOOL-12 (new), SUB-5; BLUEPRINT §4; ROADMAP post-v2 list.

### D10 — Cancellation leaves a valid transcript

**Decision.** On Ctrl-C, every tool call without a result gets
`ToolResultBlock(is_error=True, "cancelled by user")` before the session is saved.
A stream cancelled mid-generation keeps its partial text, marked interrupted, and
discards any partial tool call.
**Why.** J2 required this outcome but nothing specified how.
**Changed.** CLI-12; BLUEPRINT §4.

### D11 — Controller whitelist consolidated

**Decision.** Eight actions: `compact`, `switch_model`, `tighten_policy`,
`warn_user`, `abort`, `propose_instruction`, `propose_skill`, `noop`.
**Why.** The PRD had nine, the Blueprint and ADR-0008 listed eight different ones,
and ADR-0008 said "seven shapes". `learn` is removed by D3.
**Changed.** CTRL-4; BLUEPRINT §11.

### D12 — Config loads in M1, not M11

**Decision.** `config/schema.py` and `config/load.py` with provenance land in M1.
`init`, `doctor` and `config show` stay late, in M11.
**Why.** Credentials (M2), routing and permission rules (M3) all need config.
Without this, ten milestones would each grow their own ad-hoc config reading.
**Changed.** ROADMAP.

### D13 — Shell selection on Windows

**Decision.** `shell.program` defaults to Git Bash when found, then PowerShell 7,
then Windows PowerShell; `cmd.exe` only when configured. On Unix, `$SHELL` if it
is POSIX-compatible, otherwise `/bin/sh`. The `shell` tool's description names the
shell, so the model writes the right dialect.
**Why.** Models mostly write POSIX shell, and deny patterns like `rm -rf *` mean
nothing to `cmd.exe`.
**Changed.** TOOL-11; BLUEPRINT §15; TESTING cross-platform table.

### D14 — Instruction files are configurable

**Decision.** `instructions.files = ["AGENTS.md"]` by default, project then user
scope. Users may add `CLAUDE.md` or others. All of them are control files.
**Why.** Openness: people already maintain instruction files for other harnesses.
**Changed.** New CTX-15; BLUEPRINT §8.

### D15 — Test infrastructure fixes

**Decision.** The pairing assertion checks adjacency and one-to-one ids.
`no_network` reaches subprocess tests through a `sitecustomize.py` placed on
`PYTHONPATH` by the e2e fixture. New property tests for taint, control files,
shell segmentation, tier isolation and fact provenance.
**Why.** A monkeypatch does not cross a process boundary, so e2e tests were not
actually network-guarded, and the old pairing test accepted invalid transcripts.
**Changed.** TESTING.

### D16 — Documentation drift fixed

**Decision.** The Blueprint now includes what v0.2 added elsewhere: `core/verify.py`,
the verify step in the loop, `VerifyStarted`/`VerifyFinished` events, exit code 9
as `VerificationFailed`, the synthesis modules. `doctor` warns about iCloud Drive
as well as OneDrive and Dropbox. Example model names updated.
**Why.** The docs are the product until M0 ships; a Blueprint that lags the PRD
teaches the wrong thing.
**Changed.** BLUEPRINT throughout; CFG-5.

### D17 — Open questions resolved or added

**Resolved.** OQ-5 (JSONL plus SQLite) was already decided by ADR-0010 and is
moved to resolved.
**Added.** OQ-7 (taint scope, leaning sticky per session), OQ-8 (when to add the
Responses adapter), OQ-9 (whether `ext add` from git needs an update command).
**Changed.** PRD §12.

## Every decision in v0.4

### D18 — The headline

**Decision.** "edgar — the agent harness you can read in an afternoon. Any model.
No hidden calls. Nothing is done until it's verified."
**Why.** Each clause names a gap the field review found in existing tools, and
each is backed by a mechanism in the spec rather than a promise.
**Changed.** README, PRD §1.

### D19 — Ports and adapters, one distribution · [ADR-0022](adr/0022-ports-and-adapters.md)

**Decision.** Core imports no adapter; Provider, Tool source, Skill source,
Sandbox, Retriever and Output are ports; third-party Provider, Sandbox and
Retriever adapters register through entry points; one distribution.
**Why.** Swappable implementations without a version matrix or extra supply-chain
surface.
**Changed.** EXT-10, new EXT-11; BLUEPRINT §1, §2; ports import test.

### D20 — Sandbox backends · [ADR-0022](adr/0022-ports-and-adapters.md)

**Decision.** `shell.sandbox = none | bwrap | seatbelt | container` for `shell`,
command tools and the verify command; default `none`, recommended by `doctor`.
**Why.** Many users already isolate agents by hand; Codex's OS sandbox shows it
need not make the agent useless.
**Changed.** New PERM-15 (Should, v1); BLUEPRINT §7.5.

### D21 — No implicit models, hosts or telemetry · [ADR-0023](adr/0023-no-hidden-behaviour.md)

**Decision.** Auxiliary roles default to the main model; no host outside config
and allowed tool calls; no telemetry, update checks or remote configuration;
`doctor --network` lists reachable hosts.
**Why.** The loudest complaint in the review.
**Changed.** New PRV-15; BLUEPRINT §5.7; host-recording property test.

### D22 — The prompt is a file with a budget · [ADR-0023](adr/0023-no-hidden-behaviour.md)

**Decision.** `prompts/system.md` shipped and replaceable, no style opinions,
≤ 1,500 tokens, Core tool schemas ≤ 2,500, prompt changes in the changelog.
**Why.** A 33k-token preamble and opinions users never chose were both in the
review.
**Changed.** New CTX-16, NFR-13; `edgar prompt show`.

### D23 — Byte-stable prefix · [ADR-0023](adr/0023-no-hidden-behaviour.md)

**Decision.** Nothing above the cache breakpoint changes within a session; volatile
values go in the current turn; a test compares prefix bytes across requests.
**Why.** A date in the system prompt and re-read instruction files break the cache
on every turn and multiply cost.
**Changed.** New CTX-17.

### D24 — Visible reasoning

**Decision.** `--show-thinking` and `/thinking`; honest when a provider hides it.
**Why.** Users read reasoning to catch a wrong direction early.
**Changed.** New CLI-21.

### D25 — Memory stays lexical, with a retriever port · [ADR-0024](adr/0024-lexical-memory.md)

**Decision.** FTS5 with porter and trigram indexes, multi-term `recall`, explicit
links; `Retriever` port for plugins; no embedding model in core.
**Why.** See the answer above.
**Changed.** New MEM-24; BLUEPRINT §10.3.

### D26 — Todo, plan mode and pinned working state · [ADR-0025](adr/0025-working-state.md)

**Decision.** A `todo` tool, `/plan` and `--plan`, both pinned above the current
turn, never compacted, restored on resume.
**Why.** Plans and todo lists are the most praised practices, and other harnesses
lose them to compaction.
**Changed.** New TOOL-14, CLI-20, CTX-18; CTX-1.

### D27 — Session forks move into v1 · [ADR-0025](adr/0025-working-state.md)

**Decision.** `/fork` and `--fork ID[@TURN]`, one JSONL line per fork.
**Why.** Users ask for conversation trees; the append-only format makes them
nearly free.
**Changed.** New CLI-22; removed from "past v2".

### D28 — Small-model support

**Decision.** Deterministic, syntactic tool-call repair; a `compact` prompt profile
chosen automatically under 32k context.
**Why.** The review shows guardrails and tool errors as retry signals turn small
models from failing half their tasks to finishing nearly all; local models are
where "any model" is tested.
**Changed.** New PRV-16, PRV-17; BLUEPRINT §5.6; eval measures small-model completion.

### D29 — Deferred tool schemas

**Decision.** Above `tools.schema_budget` (4,000 tokens), MCP and extension tools
are listed by name and loaded through `tool_search`.
**Why.** MCP context bloat is the strongest practical argument against MCP.
**Changed.** New TOOL-15 (v1).

### D30 — Deterministic skill triggers

**Decision.** Edgar-only `when: { paths, keywords }` frontmatter loads a skill
without waiting for the model; `skills validate` lints descriptions for "when".
**Why.** In a published eval the agent skipped the relevant skill in over half the
cases.
**Changed.** New SKL-17 (v1); skill invocation rate in the eval.

### D31 — Supply chain and a security contact from M0

**Decision.** Trusted publishing with attestations, hash-pinned lockfile, no
install hooks, `SECURITY.md` and `security.txt` before the first release.
**Why.** A compromised provider-abstraction library and an RCE report that went
unanswered for lack of a contact, both in the review.
**Changed.** New NFR-14; ROADMAP M0.

### D32 — Terminal-native output

**Decision.** No alternate screen, native scrollback, selectable output; `edgar -c
-p` interleaves prompts with shell commands. Resolves OQ-4.
**Why.** Flicker, lost scrollback and unselectable text are the common TUI
complaints; several users want an agent that behaves like a command.
**Changed.** New CLI-23; OQ-4 resolved.

### D33 — Worktree isolation for writing subagents

**Decision.** `isolation: worktree` in agent frontmatter; the subagent returns a
branch and a diff summary.
**Why.** Users running parallel agents need them not to edit the same files.
**Changed.** New SUB-11 (Should, v1).

### Not taken from the review, and why

- **Using vendor subscriptions from edgar.** It is a terms-of-service fight edgar
  should not pick; API keys and any compatible endpoint keep users free to switch
- **A skill or extension hub.** The most downloaded skill in one hub was malware
- **Automatic memory injection.** Users report it filling context with wrong facts
- **Flashy TUIs, and an LLM router.** Both are the opposite of what the review
  asks for

---

## What did not change, and why

- **The pure-function core.** `decide()`, `select_model()`, `compute_due()`,
  `compact()` stay pure. Taint and control-file status are passed in
- **Fake provider first.** Still M1, still the highest-leverage piece of test
  infrastructure
- **Explicit `--mode` when piped, and `yolo` not reachable from config**
- **Routing, escalation and fallback as three mechanisms.** Routing rules and
  fallback move to v1, escalation to v2, and they stay separate
- **The verify gate.** It moves into Core, because "done means verified" is part
  of what makes edgar trustworthy in a pipe
- **The non-goals.** Extensions are copied folders with no index, search or
  update service, which keeps "no marketplace" true

## Not decided here

- **The `AGENTS.md` changes.** `AGENTS.md` is hand-authored and no automated
  process may modify it (ADR-0007, ADR-0008). The matching edits were proposed to
  the maintainer as a diff to apply by hand
