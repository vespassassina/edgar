# edgar — Product Requirements Document

| | |
|---|---|
| **Status** | Draft v0.4, ready to build against. v0.2 added verification and skill synthesis ([ADR-0014](adr/0014-verification-and-skill-synthesis.md)); v0.3 added release tiers, staged compression, the learning boundary, the extension model and permission hardening (ADRs 0015–0021); v0.4 adds the findings of a field review of 11,647 Hacker News comments: ports and adapters, no hidden behaviour, lexical memory, working state ([research](research/hn-2026-09.md), ADRs 0022–0025, [DECISIONS](DECISIONS.md)) |
| **Owner** | Diego |
| **Command** | `edgar` |
| **Package** | `edgar-harness` (PyPI) |
| **Licence** | AGPL-3.0-or-later ([ADR-0026](adr/0026-licence-agpl.md)) |
| **Runtime** | Python 3.12+ |
| **Platforms** | Windows, macOS, Linux |
| **Companion docs** | [BRAINSTORM](BRAINSTORM.md) · [BLUEPRINT](BLUEPRINT.md) · [TESTING](TESTING.md) · [ROADMAP](ROADMAP.md) · [DECISIONS](DECISIONS.md) · [ADRs](adr/) |

---

## 1. What this is

> **edgar — the agent harness you can read in an afternoon.**
> Any model. No hidden calls. Nothing is done until it's verified.

edgar is a small agentic harness for the terminal. It runs an LLM in a tool-using
loop, in the directory you launched it from, against whichever provider you point
it at, and it is deliberately small enough to read end to end in an afternoon.

The goal in one line: **lightweight, extensible, open and easy to use.** Lightweight
is enforced by size budgets per release tier (§5.1). Extensible means tools,
skills, agents, hooks and extensions are files (§7.15). Open means standard
formats (`AGENTS.md`, `SKILL.md`, MCP, JSONL, TOML) and any OpenAI-compatible
endpoint. Easy to use means one install command and a first run under two minutes.

It is a **teaching artifact first and a usable tool second**, and where those two
goals conflict, teaching wins. Every architectural decision in this document was
made with the question "would a competent developer understand this by reading it"
sitting next to "does this work well".

## 2. Why it exists

Existing harnesses are either toys that teach nothing beyond a `while` loop and a
function call, or production systems whose complexity hides the interesting parts.
There is a gap in the middle: a harness that implements the genuinely hard bits
honestly (tool contracts, permissions, compaction, subagents, provider
normalisation, memory) at a size a person can hold in their head.

Three concrete outcomes:

1. **Diego learns** how an agent harness actually works by building the parts that
   are usually hidden behind an SDK.
2. **Other people get a starting point** that is simple enough to fork and modify
   without first understanding 40,000 lines.
3. **A working daily tool** that composes with the rest of the shell.

## 3. Who it is for

**Primary: the curious developer.** Comfortable in a terminal, has used an agent
CLI, wants to understand the mechanism rather than the API. Will read source. The
success test is that they can add a provider or a tool without asking a question.

**Secondary: the tinkerer.** Wants agents in their workflow without writing Python.
Everything they need is markdown, TOML and shell. Never opens `src/`.

**Tertiary: the course author or workshop runner.** Needs a codebase where each
concept has one obvious home and the tests demonstrate the concept.

**Explicitly not for:** teams needing multi-user or RBAC, anyone needing an
enterprise audit story, or anyone who wants a GUI.

## 4. Principles

1. **Readable beats clever.** If a reviewer needs a comment explaining why the
   code is written that way, prefer the boring version.
2. **One obvious home per concept.** Compaction lives in one file. Permissions live
   in one file. No concept smeared across five modules.
3. **The mechanism is visible.** Prefer FTS5 over a vector store, prefer explicit
   prompt assembly over a hidden template chain, prefer a state machine you can
   print over implicit control flow. Visibility is a feature, not a compromise.
4. **Boring dependencies, few of them.** Every dependency costs startup time and
   comprehension budget. New ones need justification in a PR.
5. **Fail loudly.** Silent degradation is the enemy of a learning tool. Never
   guess when the correct action is to explain what is wrong.
6. **Machine writers never touch human files.** Anything a person hand-authors is
   off limits to every automated writer, including the controller. Machines write
   only to machine-owned locations, listed in §9.5.
7. **Humans widen, machines tighten.** Subagents, the controller, hooks and the
   model may only tighten the policy. Only a human action widens it: editing
   config, answering a prompt, passing a flag, trusting a project
   ([ADR-0021](adr/0021-humans-widen-machines-tighten.md)).
8. **Every extension surface is a file.** Tools, agents, skills, hooks,
   extensions, schedules and config are all files on disk you can edit, diff and
   commit.
9. **Open formats, no lock-in.** Instructions in `AGENTS.md`, skills in Claude's
   `SKILL.md`, tools over MCP, transcripts in JSONL, config in TOML. Anything edgar
   writes, another tool can read. The harness and the model vendor are decoupled:
   API keys and any compatible endpoint, never a vendor's subscription.
10. **No hidden behaviour.** No model, host or telemetry the user did not
    configure; the system prompt is a file you can read and replace; nothing from a
    remote source is executed ([ADR-0023](adr/0023-no-hidden-behaviour.md)).

## 5. Scope

### 5.1 Scope by release tier

Three tiers, each a release with its own size budget. Rationale in
[ADR-0015](adr/0015-release-tiers.md).

**Core (0.x)** — a harness you can read in an afternoon and use every day. ≤ 5,000 LOC.

- `-p` one-shot with stdin as attached context, `--json`, `--events`; interactive
  REPL with streaming and a status line; clean Ctrl-C
- Five providers via two adapters (OpenAI, Azure OpenAI, OpenRouter, Ollama through
  one OpenAI-compatible adapter; Anthropic through its own), plus any
  OpenAI-compatible endpoint declared in config
- Built-in tools: `read` `write` `edit` `ls` `glob` `grep` `shell` `fetch` `skill` `todo`
- Plan mode and a todo list kept as pinned session state
- Custom **command** tools (argv templates) and **HTTP** tools (request templates)
- No hidden behaviour: no implicit hosts or telemetry, the prompt as a file with a
  token budget, a byte-stable prompt prefix, visible reasoning
- Small-model support: deterministic tool-call repair and a compact prompt profile
- Skills in Claude `SKILL.md` format with progressive disclosure
- Permission engine: four modes, per-tool rules, grants, taint, control files,
  project trust
- Verification gate: a declared check must pass before a turn counts as done
- Staged context compression (spill, elide, summarise, overflow) with the pairing
  invariant held by construction
- Sessions as JSONL with `--resume` and `--continue`; SQLite for sessions index,
  grants and trust
- Turn, session and daily cost caps
- Layered config with provenance
- Offline test suite, provider contract suite, CI on three OSes

**v1.0** — extensible, remembers, and freezes the extension formats. ≤ 8,000 LOC total.

- Facts memory: `/remember`, model-proposed facts confirmed by the user, pinned set
  plus `recall`, `memory edit`, session search
- MCP client (stdio and Streamable HTTP)
- Subagents as markdown + frontmatter, parallel fan-out, per-agent model and tools
- Declarative routing rules and provider fallback
- Hooks, extension bundles, provider plugins, `edgar.run()` embedding API
- Ports for sandboxes (bubblewrap, Seatbelt, containers) and retrievers
- Session forks; deferred tool schemas; deterministic skill triggers
- `edgar init`, `edgar doctor`, `config show --resolved`
- Documentation: guided tour, cookbook, extending guide, per-concept explainers

**v2.0** — learns and runs unattended. ≤ 11,000 LOC total, and removable: v1
passes its suite with the v2 packages deleted [NFR-12].

- Autolearn from typed text and templated error facts; `history.md` with
  out-of-band condensing; experience telemetry and `stats`
- Controller on deterministic triggers with typed proposals
- Skill synthesis from verified work, distill, optional curator
- Escalation, `route suggest`, budget-aware downgrade
- Scheduling via `tick`, host installers, `schedule_self`
- MCP OAuth for remote servers

**Requirement map.** IDs keep their numbers; this table says which tier delivers
them. A constraint (for example MEM-9) applies from the tier in which its mechanism
first lands.

| Area | Core | v1.0 | v2.0 |
|---|---|---|---|
| CLI | 1–12, 15–21, 23; CLI-14 subset `/help /model /mode /compact /cost /clear /plan /go /thinking /quit` | 13, 22; rest of 14 | — |
| Providers | 1–13, 15–17 | 14 | — |
| Tools | 1–6, 9 (without MCP), 10–14; TOOL-5 built-ins listed above | 7, 8, 15; `task` `remember` `recall` | `schedule_self` |
| Permissions | 1–14 | 15 | — |
| Context | 1–9, 11–18 | 10 | — |
| Subagents | — | 1–11 | — |
| Skills | 1–5, 7 (`list`, `validate`) | 17 | 6, 7 (rest), 8–16 |
| Memory | — | 1–7, 10, 11, 15, 20, 21, 23, 24 | 8, 12–14, 16–19, 22 |
| Controller | — | — | 1–13 |
| Routing | 1 (static roles) | 2–4, 6, 7, 9, 10 | 5, 8, 11, 12 |
| Scheduling | — | — | 1–12 |
| Budget | 1–3, 5, 6 | 4 | — |
| Config | 1–3, 6–8 | 4, 5 | — |
| Verification | 1–7 (sources arrive with their features) | — | — |
| Extensions | 11 (the ports rule holds from M0) | 1–10 | — |
| Non-functional | 1–3, 6, 9, 13, 14 | 4, 5, 7, 8, 10, 11 | 12 |

### 5.2 Explicit non-goals

Written down so scope creep has something to argue with.

| Not doing | Why |
|---|---|
| MCP **server** mode | Different product. Consumes attention, teaches nothing new. |
| Server / daemon / HTTP API | Fights the unix story. Host schedulers already solve this. |
| RAG index or vector store | Embeddings hide the retrieval mechanism. FTS5 is visible and enough. |
| Multi-user, auth, RBAC | Single-user tool by design. |
| GUI or web UI | Terminal is the product. |
| Fine-tuning / training | Out of scope entirely. |
| Full TUI framework | Line-oriented output pipes cleanly. See OQ-4. |
| Plugin marketplace or skill hub | Files in a folder, discovered on disk. That is the plugin system. Skills and extensions are copied in (`edgar ext add` copies a path or git URL), never installed from an index, search or update service. |
| Provider count race | Five providers, deeply correct, beats fifty shallow. |
| Agent-to-agent protocols | Subagents are function calls, not a network. |
| Messaging gateway (Telegram, Slack, Discord…) | Needs a long-running process. A `session_end` hook covers delivery. |
| User modelling (Honcho-style profiles) | A model of the user built by a model is invisible state. Facts with provenance are the visible version. |
| Memory nudges in the system prompt | Turns autolearn back into model judgement. Learning is triggered deterministically from the three sources in MEM-8. |

### 5.3 Deferred past v2

Notifications (desktop/Teams/webhook; a `session_end` hook covers the gap),
concurrent execution of independent read-only tool calls within one response
(calls run in order; consecutive `task` calls already fan out, TOOL-12),
remote/shared memory, embedding or graph retrievers in core (a retriever port
exists for plugins, ADR-0024), a TUI mode, `git` and language-server tools,
generating HTTP tools from an OpenAPI spec, Homebrew and Scoop manifests, image and
multimodal input.

## 6. User journeys

Each journey names the tier in which its acceptance test first passes.

### J1 — First run (v1; Core works with env vars and no `init`)

```
$ cd ~/projects/thing
$ uvx edgar-harness init
```

`init` writes `.edgar/config.toml`, an `AGENTS.md` stub, and a `.gitignore`
fragment. It detects available credentials from the environment, offers to store
them, and tells you exactly which providers are usable and which are not and why.
It never writes a secret into a file that could be committed.

**Acceptance:** on a machine with only `OLLAMA_HOST` set, `init` completes,
reports Ollama available and the other four unconfigured with the exact env var
each needs.

### J2 — Interactive session, the daily driver (Core)

```
$ edgar
edgar · gpt-5 · ~/projects/thing · ask mode
› find the retry logic and tell me if it handles 429s
```

Streams the answer. The status line on stderr shows the current activity, elapsed
time, token count and cost. Tool calls that need permission stop and ask, inline,
with the exact command or path shown. Ctrl-C once interrupts the turn and keeps
the session; twice exits cleanly.

**Acceptance:** interrupting mid-stream leaves a resumable session with no partial
or orphaned tool blocks in the transcript.

### J3 — Piped, composed with other tools (Core)

```
$ git diff | edgar -p "review this for bugs, output markdown" --mode read-only
$ edgar -p "summarise" --json < notes.txt | jq -r .result
$ fd -e py | edgar -p "which of these files handle auth?" --mode read-only
```

stdout carries only the result. The status line does not render because stderr is
not a TTY, or because output is being consumed. Exit code is meaningful.

**Acceptance:** `edgar -p "hi" > out.txt 2>/dev/null` produces a file containing
only the model's answer, no ANSI codes, no status text.

### J4 — Scoped models via subagents (v1)

`.edgar/agents/explorer.md` declares a cheap fast model with read-only tools.
`.edgar/agents/reviewer.md` declares an expensive model with a narrow allowlist.
The main agent fans out three explorers in parallel, gets three summaries back,
then hands the synthesis to the reviewer. No Python written.

**Acceptance:** three parallel subagents on different providers complete, each
respecting its own allowlist, with the status line showing all three concurrently
and total cost attributed per agent.

### J5 — Memory over time (v1, autolearn in v2)

Session one, in v1, you type `/remember we use pytest, not unittest`. Or the agent
calls `remember` after you say it, and at the end of the turn edgar asks
`1 fact proposed: "tests use pytest, not unittest" — save? [y/N]`. In v2 you do
not need either: you correct the agent, and autolearn records the correction from
the text you typed with provenance `user-feedback`. Session four, the fact is in
the pinned set and the agent gets it right unprompted. You run `edgar memory edit`,
see it in markdown, tweak the wording, save, and it writes back.

**Acceptance:** a fact from `/remember` or a confirmed proposal survives a session
restart, appears in `memory list`, is editable via `memory edit`, and is revertible
via `memory undo`. A proposal the user declines is never injected. In v2, a fact
learned from a typed correction does the same, and no fact becomes active from
tool output, piped stdin or an attached file.

### J6 — Scheduled run (v2)

```
$ edgar schedule add nightly --cron "0 3 * * *" --prompt "audit deps for CVEs" \
    --mode read-only --agent security
$ edgar install-tick
```

One host entry now calls `edgar tick` every minute. At 03:00 the run fires
non-interactively, writes a transcript to `.edgar/runs/`, and fires the entry's
`session_end` hook if configured.

**Acceptance:** with a frozen clock, `tick` fires a due schedule exactly once,
does not fire it again in the same window, and catches up correctly after a
simulated 6-hour sleep according to the configured catch-up policy.

### J7 — Controller intervention (v2)

Context crosses 70% of the window. The deterministic check trips. A cheap model is
invoked, sees the session summary, and proposes `compact` with a reason. In `auto`
mode it runs and prints one line saying what it did. In `ask` mode you are shown
the proposal first.

**Acceptance:** the controller never executes an action outside the whitelist, and
every mutation it makes appears in `edgar controller log` with a working revert.

### J8 — A verified procedure becomes a skill (v2)

```
$ edgar -p "bump the httpx pin and fix whatever breaks" --mode auto --verify "just check"
```

The agent edits `pyproject.toml`, runs the tests, hits two failures, fixes them. It
stops calling tools; the harness runs `just check`, which passes. The turn used
eleven tool calls and recovered from errors, so the synthesis trigger trips. A cheap
model sees the outline of the run (the typed prompt, tool calls in order, error
records, the passing check) but none of the tool output and no error text, and
writes `dependency-bump/SKILL.md`. With
`skills.synthesis = "propose"` it lands in `.edgar/proposals/` for
`edgar controller apply`. With `"auto"` it lands in `.edgar/skills/learned/` and the
next session sees it in the skill index tagged `[learned]`.

**Acceptance:** a turn that ends with a failing check produces no skill; a verified
turn over the thresholds produces exactly one proposal; the synthesiser's input
contains no tool output; in `auto` mode no hand-authored skill file changes.

### J9 — Giving the agent a CLI and an API (Core; bundled as an extension in v1)

You want the agent to read GitHub issues and check a status API. No Python:

```toml
# .edgar/tools/gh_issue.toml
name = "gh_issue"
description = "Read a GitHub issue with the gh CLI."
argv = ["gh", "issue", "view", "{number}", "--json", "title,body,comments"]
read_only = true
[input]
type = "object"
required = ["number"]
properties.number = { type = "integer" }
```

```toml
# .edgar/tools/status.toml
name = "service_status"
description = "Current status of a service from the status API."
method = "GET"
url = "https://status.example.com/api/v2/services/{service}"
headers = { Authorization = "Bearer ${env:STATUS_API_TOKEN}" }
read_only = true
[input]
type = "object"
required = ["service"]
properties.service = { type = "string" }
```

The first time edgar runs in this project it lists the two tools and asks you to
trust the project. `edgar tools list` shows both. In v1 you move them, plus a skill
that explains when to use them, into `.edgar/extensions/github/` with an
`extension.toml`, and a colleague copies the folder with `edgar ext add`.

**Acceptance:** a command tool's argument containing `; rm -rf ~` reaches `gh` as
one literal argv element; an HTTP tool cannot be made to call a different host;
the API token never appears in the transcript, events or logs; in a non-interactive
run of an untrusted project, edgar exits 3 and names `edgar trust`.

## 7. Functional requirements

Requirements are numbered for traceability. Each milestone in
[ROADMAP.md](ROADMAP.md) references the IDs it delivers.

### 7.1 CLI and I/O

| ID | Requirement | Priority |
|---|---|---|
| CLI-1 | Default invocation with no args and a TTY starts the interactive REPL | Must |
| CLI-2 | `-p/--prompt` runs one turn non-interactively and exits | Must |
| CLI-3 | Piped stdin and `@path` file attachments are **attached context**, never the prompt itself, and are tagged `attached` so they are never a learning source (MEM-9) | Must |
| CLI-4 | Running without a TTY and without `-p` is a usage error (exit 2) with a message naming `-p` | Must |
| CLI-5 | Result to stdout; status line, logs and prompts to stderr | Must |
| CLI-6 | Status line renders only when stderr is a TTY | Must |
| CLI-7 | `--json` emits a single JSON object: result, usage, cost, tools used, exit reason | Must |
| CLI-8 | `--quiet` suppresses the status line even on a TTY | Must |
| CLI-9 | Non-interactive runs require an explicit `--mode`; absent, exit 3 with an explanatory error | Must |
| CLI-10 | Defined exit codes (§9.3) | Must |
| CLI-11 | `--resume [id]` and `--continue` restore a prior session | Must |
| CLI-12 | Ctrl-C once cancels the turn, twice exits; no corrupted state either way. Every tool call without a result gets `ToolResultBlock(is_error=True, "cancelled by user")` before the session is saved; a stream cut mid-generation keeps its partial text marked interrupted and discards any partial tool call | Must |
| CLI-13 | Mid-turn steering: typing while streaming queues input for the next turn | Should |
| CLI-14 | Slash commands in REPL: `/help /model /mode /compact /plan /go /thinking /fork /remember /memory /skills /agents /tools /cost /clear /resume /quit` | Must |
| CLI-15 | `NO_COLOR` and `--no-color` honoured | Must |
| CLI-16 | `--cwd` overrides the working directory; default is the launch directory | Must |
| CLI-17 | `--verify CMD` declares the verification command for this run, overriding every other source (§7.14) | Must |
| CLI-18 | `--events` writes the event stream to stdout as JSON Lines, one event per line, for programs embedding edgar; mutually exclusive with `--json` | Must |
| CLI-19 | `edgar trust [--yes]` records trust for the current project's executable config; `--no-project-exec` runs with that config disabled (PERM-13) | Must |
| CLI-20 | Plan mode: `/plan` in the REPL or `--plan` with `-p` runs in `read-only` mode and writes the plan to `sessions/<id>/plan.md`; `/go` returns to the previous mode with the plan pinned (CTX-18, [ADR-0025](adr/0025-working-state.md)) | Must |
| CLI-21 | `--show-thinking` and `/thinking` render reasoning deltas where the provider exposes them, and say so where it does not; `--json` and `--events` include reasoning when requested | Must |
| CLI-22 | Session forks: `/fork` in the REPL and `edgar --fork ID[@TURN]` start a new session whose JSONL begins with a `fork` record naming the parent and turn; the parent's messages are replayed, not copied | Must |
| CLI-23 | Terminal-native output: no alternate screen; output stays in the terminal's own scrollback and is selectable; the status line is the only redrawn element; `edgar -c -p "…"` continues the last session from the shell so prompts interleave with ordinary commands | Must |

### 7.2 Providers

| ID | Requirement | Priority |
|---|---|---|
| PRV-1 | OpenAI-compatible adapter serving OpenAI, Azure OpenAI, OpenRouter and Ollama | Must |
| PRV-2 | Dedicated Anthropic adapter | Must |
| PRV-3 | Per-provider quirks table: tool-call format, system prompt placement, streaming shape, max tokens, parallel tool calls, caching | Must |
| PRV-4 | Provider modules import lazily; no SDK or HTTP client import until a model resolves | Must |
| PRV-5 | Token streaming with text, tool-call and reasoning deltas normalised to one event stream | Must |
| PRV-6 | Usage and cost reported per request; approximate where the provider omits it, flagged as approximate | Must |
| PRV-7 | Retry with exponential backoff and jitter on 429 and 5xx; respect `Retry-After` | Must |
| PRV-8 | Anthropic `cache_control` on the stable prompt prefix | Should |
| PRV-9 | Model strings are `provider/model`, e.g. `anthropic/claude-sonnet-5`, `ollama/qwen3` | Must |
| PRV-10 | Capability probe: adapters declare tool support, streaming, reasoning; harness degrades explicitly with a warning, never silently | Must |
| PRV-11 | Adding a provider requires at most one new module plus one registry entry, and for an OpenAI-compatible server only a config block (PRV-12) | Must |
| PRV-12 | User-defined providers: a `[providers.NAME]` block with `kind = "openai-compatible"`, `base_url`, optional `api_key_env` and any quirk overrides makes `NAME/model` resolvable. Unknown quirks default conservatively and are capability-probed on first use ([ADR-0020](adr/0020-provider-portability.md)) | Must |
| PRV-13 | `ThinkingBlock` carries its `origin` (adapter family and model). Adapters serialise only same-family reasoning and drop the rest with one `ReasoningDropped` event; a mid-turn switch to another family runs with reasoning off until the next user turn, announced | Must |
| PRV-14 | Provider plugins register through the `edgar.providers` entry point, read only when a model string names an unknown provider; the contract suite ships as `edgar.testing.contract` for plugin authors | Must |
| PRV-15 | **No implicit models, hosts or telemetry.** Every request goes to a model named in config or on the command line; auxiliary roles (compactor, controller, condenser) default to the main model; edgar contacts no host except those in config and those reached by an allowed tool call; no telemetry, update checks or remote configuration. `edgar doctor --network` lists every host the config can reach ([ADR-0023](adr/0023-no-hidden-behaviour.md)) | Must |
| PRV-16 | Tool-call repair: when a model emits a malformed tool call (JSON in a code fence, trailing text, a single JSON object in plain text where the provider has no native tool format), the adapter applies a fixed, deterministic syntactic repair; anything it cannot repair returns to the model as a validation error (TOOL-2). Repairs are counted in usage and events | Must |
| PRV-17 | Prompt profiles: `full` or `compact`. `compact` uses `prompts/compact.md`, exposes Core built-ins only unless configured, and lowers `compact_at` and `compact_to` by 0.1. Chosen automatically for models with `max_context` under 32k, overridable per model | Must |

### 7.3 Tools

| ID | Requirement | Priority |
|---|---|---|
| TOOL-1 | Tool contract is MCP-shaped: name, description, JSON Schema input, content-block output | Must |
| TOOL-2 | Arguments validated against schema before execution; validation errors return to the model as a tool error, not an exception | Must |
| TOOL-3 | Per-tool timeout; timeout returns a tool error and cancels the underlying work | Must |
| TOOL-4 | Output over `tools.max_output_tokens` is head/tail truncated with an explicit marker, and the full output is spilled to `.edgar/sessions/<id>/blobs/<tool_use_id>.txt`, named in the marker so the model can `read` it with an offset (CTX-13) | Must |
| TOOL-5 | Built-ins: `read` `write` `edit` `ls` `glob` `grep` `shell` `fetch` `skill` (Core); `task` `remember` `recall` (v1); `schedule_self` (v2) | Must |
| TOOL-6 | Custom tools declared in TOML, of two kinds: **command** (an `argv` template; arguments substituted as whole argv elements, never through a shell) and **HTTP** (method, URL and body templates; the host is fixed by the template; `${env:NAME}` resolves only in base URL and headers, never from model arguments, and is redacted everywhere). Both carry a JSON Schema, a timeout and an optional `read_only` flag ([ADR-0018](adr/0018-extension-model.md)) | Must |
| TOOL-7 | MCP client: stdio and Streamable HTTP transports, discovery, namespacing as `mcp__server__tool`. Legacy HTTP+SSE is not supported; remote servers take static headers from env in v1, OAuth in v2. Server annotations never drive permission decisions | Must |
| TOOL-8 | MCP servers spawn lazily on first use, not at startup | Must |
| TOOL-9 | Tool names collide-resolve deterministically: project custom > user custom > extensions (by name) > MCP > built-in, with a startup warning | Must |
| TOOL-10 | Every tool call is cancellable | Must |
| TOOL-11 | `shell` runs `shell.program`: on Windows, Git Bash when found, then PowerShell 7, then Windows PowerShell (`cmd.exe` only when configured); elsewhere `$SHELL` if POSIX-compatible, otherwise `/bin/sh`. The tool description names the shell | Must |
| TOOL-12 | Tool calls from one model response execute in order. Consecutive `task` calls form one fan-out group and run concurrently (SUB-5). Permission prompts from any agent go through one queue and are asked one at a time, labelled with the agent | Must |
| TOOL-13 | Results from network-sourced tools (`fetch`, HTTP tools, MCP tools) are marked untrusted and set the session taint (PERM-11) | Must |
| TOOL-14 | `todo` built-in: one call replaces the whole list of `{text, status}` items with status `pending`, `in_progress` or `done`; emits `TodoUpdated`; the list is pinned working state (CTX-18) | Must |
| TOOL-15 | Deferred tool schemas: when the schemas of all exposed tools exceed `tools.schema_budget` tokens (default 4,000), MCP and extension tools are listed by name and one line, and their schemas are loaded on demand through a `tool_search` meta-tool. Built-ins are never deferred | Must |

### 7.4 Permissions

| ID | Requirement | Priority |
|---|---|---|
| PERM-1 | Four modes: `read-only`, `ask`, `auto`, `yolo` | Must |
| PERM-2 | Per-tool rules of `allow` / `ask` / `deny` override the mode | Must |
| PERM-3 | Write and edit paths are glob-scoped, defaulting to the working directory subtree | Must |
| PERM-4 | Shell commands matched against allow and deny pattern lists; deny always wins | Must |
| PERM-5 | Path resolution defeats traversal, symlink escape and UNC tricks before matching | Must |
| PERM-6 | Interactive `ask` offers once / session / always. "Always" stores a grant in the project's `edgar.db`, never in config; `edgar permissions list` and `revoke ID` manage grants, and `config show --resolved` shows them with origin `grant` | Must |
| PERM-7 | Non-interactive never prompts; a decision requiring a prompt is a denial with exit 5 | Must |
| PERM-8 | **Humans widen, machines tighten.** No automated component (model, tool, subagent, controller, learner, hook) may widen policy; subagent policy may only narrow relative to its parent ([ADR-0021](adr/0021-humans-widen-machines-tighten.md)) | Must |
| PERM-9 | `yolo` requires an env var or an explicit flag with a typed confirmation; never reachable by config alone | Must |
| PERM-10 | Every decision is logged with rule, subject and outcome | Must |
| PERM-11 | **Taint.** `decide()` takes `tainted: bool`. The session is tainted, for the rest of the session, once an untrusted result (TOOL-13) enters the transcript; the status line shows it. In `auto` mode only, while tainted, the mode default for `shell`, command tools not marked `read_only` and network-egress tools becomes Ask (deny when non-interactive). Explicit rules and grants still apply | Must |
| PERM-12 | **Control files** (configured instruction files, `config.toml` at both scopes, `schedules.toml`, `.edgar/{agents,tools,extensions}/**`, `.edgar/skills/**` except `learned/`, and user-scope equivalents): `write` and `edit` are Ask in every mode except `yolo`, deny when non-interactive, in the hard layer rules cannot override. A hash of control files is stored at session end; the next session warns if they changed while a session was running | Must |
| PERM-13 | **Project trust.** Executable project config (hooks, MCP servers, command and HTTP tools, extensions, `verify.command`) runs only in a trusted project. Interactive first use lists it and asks; trust is keyed by project path and a hash of that config and is asked again when the hash changes. Non-interactive and untrusted exits 3 naming `edgar trust` and `--no-project-exec`. User-scope config is trusted | Must |
| PERM-14 | Shell commands are split on `;` `&&` `||` `\|` and newlines after whitespace normalisation; denied if any segment matches a deny pattern, auto-allowed only if every segment matches an allow pattern; command substitution is never auto-allowed. Documented as a speed bump, not a boundary | Must |
| PERM-15 | Sandbox port: `shell.sandbox = "none" \| "bwrap" \| "seatbelt" \| "container"` runs `shell`, command tools and the verify command inside the chosen backend, with the project and blob directories writable and network per the permission decision. Default `none`; `doctor` recommends an available backend; an unavailable configured backend fails loudly ([ADR-0022](adr/0022-ports-and-adapters.md)) | Should |

### 7.5 Context and compaction

Rationale for CTX-3 to CTX-14 in [ADR-0016](adr/0016-context-pipeline.md).

| ID | Requirement | Priority |
|---|---|---|
| CTX-1 | Deterministic prompt assembly, most stable first: system prompt → tool schemas → instruction files → pinned facts → skill index → *(cache breakpoint)* → rolling summary → transcript → working state (CTX-18) → current turn. Everything above the breakpoint is fixed for the session | Must |
| CTX-2 | `edgar context show` prints the assembled prompt with per-section token counts | Must |
| CTX-3 | Autocompact, on by default (`context.autocompact`): runs before any request, including mid-turn between units, once the prompt crosses `context.compact_at` of the usable window (default 0.70), and compacts down to `context.compact_to` (default 0.50) | Must |
| CTX-4 | **Invariant:** every assistant message containing tool calls is immediately followed by exactly one tool message whose result ids equal the call ids, one-to-one. Thinking blocks in the turn in progress are never altered. Checked before every request in debug builds | Must |
| CTX-5 | Never compacted: system prompt, instruction files, pinned facts, skill index, the first user message, and the unit in progress. The last `context.keep_last_turns` turns (default 4) are exempt from S1 and S2 but not from S3 | Must |
| CTX-6 | The rolling summary has a fixed shape: *Goal*, *Decisions*, *Files touched*, *Open threads*, *Errors seen*, *Blobs worth re-reading*. A previous summary is folded into the new one, so there is at most one | Must |
| CTX-7 | Manual `/compact` with optional focus instruction | Must |
| CTX-8 | Compaction is idempotent: after any compaction the prompt is below `compact_to`, so compacting again is a no-op | Must |
| CTX-9 | Token counting exact where the provider reports usage, approximate with per-provider correction otherwise (OQ-3) | Must |
| CTX-10 | `edgar sessions compact ID [--focus TEXT]` compacts a stored session outside the REPL, appending a compaction record the next `--resume` picks up | Should |
| CTX-11 | Compaction runs in stages until under target, and every stage operates on whole units (an assistant tool-call message plus its tool message) and whole turns: **S1 elide** old tool-result content to a one-line stub (tool, argument preview, size, blob path) and drop thinking blocks from completed turns; **S2 summarise** the oldest completed turns with one cheap-model call; **S3 overflow** (CTX-12) | Must |
| CTX-12 | If pinned content alone exceeds the usable window, elide inside the recent turns except the unit in progress; if still over, raise `ContextOverflow` (exit 1) with a hint naming `/compact`, `context.keep_last_turns` and a larger-context model. The current user input is never dropped silently | Must |
| CTX-13 | **S0 spill** at tool execution (TOOL-4). Blobs live under `sessions/`, which is machine-owned and gitignored | Must |
| CTX-14 | Compress the prompt, never the record: the JSONL is append-only and a compaction appends a record naming the replaced unit range and the summary; `--resume` rebuilds the compacted view | Must |
| CTX-15 | `instructions.files` (default `["AGENTS.md"]`) lists the instruction files read at project then user scope; users may add `CLAUDE.md` or others. All are control files (PERM-12) | Must |
| CTX-16 | The base system prompt ships as `prompts/system.md` (and `prompts/compact.md`), shown by `edgar prompt show`, replaceable by `.edgar/prompts/system.md` (a control file). It carries no style opinions; changes to shipped prompts are listed in the changelog | Must |
| CTX-17 | **Byte-stable prefix.** Nothing above the cache breakpoint changes within a session; the date, time and other volatile values go in the current turn. A test asserts the serialised prefix is byte-identical across requests until a compaction | Must |
| CTX-18 | **Working state** — the plan (CLI-20) and the todo list (TOOL-14) — is rendered in one block just above the current turn: below the cache breakpoint, outside the compactable transcript, recorded in the JSONL and restored by `--resume` | Must |

### 7.6 Subagents

| ID | Requirement | Priority |
|---|---|---|
| SUB-1 | Defined as markdown + YAML frontmatter: name, description, model, tools, mode, budget, optional `verify`, prompt | Must |
| SUB-2 | Discovered at `./.edgar/agents/` then `~/.edgar/agents/`; project wins | Must |
| SUB-3 | Fresh context: system prompt plus the parent's task description only | Must |
| SUB-4 | Returns a summary, not a transcript; full transcript persisted for inspection | Must |
| SUB-5 | Parallel fan-out: consecutive `task` calls in one response run concurrently (TOOL-12), capped by `subagents.max_parallel`, default 4 | Must |
| SUB-6 | Max depth default 2, hard ceiling 5; exceeding is a tool error, not a crash | Must |
| SUB-7 | Budget inherited from parent remainder; exhaustion returns a partial result flagged as such | Must |
| SUB-8 | Failures surface to the parent as tool errors | Must |
| SUB-9 | Status line shows concurrent subagents with individual state | Must |
| SUB-10 | Recursion guard: an agent cannot spawn itself directly or via a cycle | Must |
| SUB-11 | `isolation: worktree` in agent frontmatter runs a write-capable subagent in its own git worktree; it returns a branch name and a diff summary instead of editing the parent's working copy | Should |

### 7.7 Skills

| ID | Requirement | Priority |
|---|---|---|
| SKL-1 | Claude-compatible `SKILL.md`: YAML frontmatter with `name` and `description`, markdown body. Optional edgar-only `verify` field (§7.14), ignored by other harnesses | Must |
| SKL-2 | Progressive disclosure: only name and description in context until invoked | Must |
| SKL-3 | Discovery at bundled, `~/.edgar/skills/`, `./.edgar/skills/`, enabled extensions' `skills/`, and the machine-owned `learned/` subfolder of each scope; project wins, hand-authored wins over learned on a name collision. Frontmatter parsed with `yaml.safe_load` | Must |
| SKL-4 | The `skill` tool loads the body on demand | Must |
| SKL-5 | Skill folders may bundle scripts and resources, path-resolvable from the body | Must |
| SKL-6 | Per-skill `HISTORY.md` in the skill folder acts as durable scoped notes | Must |
| SKL-7 | `edgar skills list [--learned]`, `validate`, `distill NAME`, `curate`, `forget NAME` | Must |

**Skill synthesis.** Rationale in
[ADR-0014](adr/0014-verification-and-skill-synthesis.md). Skills are procedures the
agent follows as instructions, unlike facts, which are injected as data (MEM-7). That
is why synthesis gets stricter rules than fact autolearn.

| ID | Requirement | Priority |
|---|---|---|
| SKL-8 | Synthesis triggers are deterministic checks in the controller's post-turn gate (CTRL-1), read from experience telemetry: (a) verified success after ≥ `skills.synthesis_triggers.min_tool_calls` tool calls, default 5; (b) verified success after ≥ 1 tool error in the turn; (c) a user correction during the turn; (d) the same task shape recurring ≥ `skills.synthesis_triggers.min_repeats` times across sessions with no skill covering it, default 3 (OQ-6) | Must |
| SKL-9 | Synthesiser input is the outline of the run only: user-typed prompt and corrections, tool names and arguments in order, `ErrorRecord`s (MEM-22), verification result. **Never tool output bodies, error text or fetched content.** Extends MEM-9 ([ADR-0017](adr/0017-learning-boundary.md)) | Must |
| SKL-10 | Mode `skills.synthesis = "off" \| "propose" \| "auto"`, default `"propose"`. `propose` emits the controller's `propose_skill` as a diff to `.edgar/proposals/`, applied by `edgar controller apply <id>` | Must |
| SKL-11 | `auto` writes new and patched skills straight into `.edgar/skills/learned/`, which is machine-owned. It only fires on triggers (a), (b) and (d) with a verified outcome; trigger (c) and unverified turns still produce proposals. Patches to hand-authored skills are always proposals, in every mode | Must |
| SKL-12 | Learned skills carry provenance in frontmatter (`learned: true`, source session, trigger, created) and appear as `[learned]` in the skill index. Every write is a controller mutation with a revert (CTRL-7); `skills forget NAME` archives to `learned/.archive/` | Must |
| SKL-13 | **Disclaimer for `auto`.** Each session start prints to stderr: *"skills.synthesis = auto: edgar writes skills that future sessions follow as instructions, without your review. A mistake, or an instruction injected into a task, that reaches a learned skill persists until you remove it. Review with `edgar skills list --learned`."* `edgar doctor` reports the mode, and `edgar init` never enables it | Must |
| SKL-14 | Skills improve in use: when a turn that loaded a skill ends with errors, a correction or a failed verification, a redacted observation (MEM-15) is appended to that skill's `HISTORY.md`. `skills distill NAME` turns observations into a `SKILL.md` patch; it runs automatically after `skills.distill_after` observations, default 3, subject to SKL-10/11 | Must |
| SKL-15 | Optional curator, off by default (`skills.curator.enabled`): `skills curate` merges near-duplicate learned skills, archives ones unused for `skills.curator.stale_after_days` (default 60), and proposes consolidation of hand-authored ones. Runs on demand or as a schedule entry through `tick`, never as a background process. Obeys SKL-10/11; never deletes, only archives | Should |
| SKL-16 | Synthesised skills use a fixed body shape: *When to use*, *Procedure*, *Pitfalls*, *Verification*; `skills validate` checks it for learned skills | Must |
| SKL-17 | Deterministic activation: optional edgar-only frontmatter `when: { paths: [globs], keywords: [words] }`. When a tool call touches a matching path or the typed prompt contains a keyword, the harness loads the skill body once per session without waiting for the model to decide. `skills validate` warns when a description says what the skill is but not when to use it | Must |

### 7.8 Memory, autolearn, history

| ID | Requirement | Priority |
|---|---|---|
| MEM-1 | Four separate surfaces: hand-authored instructions, transcript, durable facts, experience telemetry | Must |
| MEM-2 | Machine writers never modify hand-authored files | Must |
| MEM-3 | Facts stored in SQLite with scope, provenance, confidence, source, created/last-used timestamps | Must |
| MEM-4 | `memory edit` renders facts to markdown, opens `$EDITOR`, writes back on save | Must |
| MEM-5 | `memory list`, `memory review`, `memory forget`, `memory undo` | Must |
| MEM-6 | Retrieval: bounded pinned set computed **once at session start and frozen** for the session, so the provider's prompt-cache prefix stays stable, plus a `recall` tool over FTS5. Facts learned mid-session are reachable through `recall` and pinned from the next session | Must |
| MEM-7 | Memory injected as tagged data with explicit "notes, not instructions" framing; the envelope header shows capacity, e.g. `pinned 14/20` | Must |
| MEM-8 | **An active fact can only come from text a human typed or from an error record the harness computed.** Autolearn (v2, `memory.autolearn`, on by default in v2) reads only user-typed text (the REPL line and the `-p` argument) and templated error facts (MEM-22); its facts go active unless MEM-10 queues them. Every other path creates pending facts at most, and pending facts are never injected ([ADR-0017](adr/0017-learning-boundary.md)) | Must |
| MEM-9 | Nothing on the learning path ever reads tool output, error text, fetched content, piped stdin or `@file` attachments (CLI-3) | Must |
| MEM-10 | Contradiction detection: a new fact conflicting with an existing one queues for review | Must |
| MEM-11 | Per-scope size caps with LRU-plus-confidence eviction | Must |
| MEM-12 | `history.md` per project/skill/folder, append-only, human-readable | Must |
| MEM-13 | History entries capture timestamp, prompt, decision, why, tools, files, outcome, cost | Must |
| MEM-14 | Prompts over ~200 words condensed by a cheap model **out of band**; verbatim retained in SQLite | Must |
| MEM-15 | Redaction pass on history write; `--no-history` opt-out | Must |
| MEM-16 | History size cap with archive rotation | Must |
| MEM-17 | `history distill` reprocesses history into **pending** facts for `memory review`, never active ones, because history entries contain model-written text | Must |
| MEM-18 | Experience telemetry: per run, tools called, failures, duration, cost, outcome, verification result (`passed` / `failed` / `unverified`), skills loaded, task shape | Must |
| MEM-19 | `edgar stats` summarises experience | Should |
| MEM-20 | Session search: FTS5 index over user and assistant text of stored transcripts, exposed as `recall(scope="sessions")`, returning matching messages with session id and turn. Tool output is not indexed | Should |
| MEM-21 | Model-proposed facts: the `remember` tool creates a **pending** fact. At turn end an interactive session asks `N facts proposed: … save? [y/N]`; non-interactive runs leave them for `memory review` | Must |
| MEM-22 | Error facts are templated from `ErrorRecord` fields the harness computes (tool, kind, exit code, `argv[0]` basename restricted to `[A-Za-z0-9._-]`), never generated from error text, and pinned only after repeats | Must |
| MEM-23 | Human-authored facts: `/remember TEXT` in the REPL and `edgar memory add TEXT` create active facts with provenance `user` | Must |
| MEM-24 | Recall is lexical and deterministic: FTS5 with `porter` and `trigram` indexes, BM25 ranking, scope and recency as tie-breakers. `recall` accepts a list of terms so the model supplies synonyms. Retrieval goes through the `Retriever` port; plugins may register other retrievers via `edgar.retrievers`, and core never loads an embedding model ([ADR-0024](adr/0024-lexical-memory.md)) | Must |

### 7.9 Controller

| ID | Requirement | Priority |
|---|---|---|
| CTRL-1 | Deterministic checks after each turn: token fraction, consecutive error streak, budget burn rate, output size, wall-clock, and the skill synthesis triggers (SKL-8) | Must |
| CTRL-2 | Controller model invoked only when a check trips; opt-in `always` mode | Must |
| CTRL-3 | Controller has a hard-limited tool set and cannot call arbitrary tools | Must |
| CTRL-4 | Returns typed proposals from a fixed whitelist of eight: `compact` `switch_model` `tighten_policy` `warn_user` `abort` `propose_instruction` `propose_skill` `noop`. There is no `learn` action (ADR-0017); when invoked for synthesis the controller receives the SKL-9 outline, never its session summary | Must |
| CTRL-5 | Proposals schema-validated; malformed proposals discarded and logged | Must |
| CTRL-6 | Config and policy changes dry-run by default | Must |
| CTRL-7 | Every mutation logged with before/after and a revert path | Must |
| CTRL-8 | **Policy may only tighten, never loosen** | Must |
| CTRL-9 | Controller runs on a cheap model configured separately from the main model | Must |
| CTRL-10 | `edgar controller log` and `edgar controller revert <id>` | Must |
| CTRL-11 | Controller failure never fails the turn | Must |
| CTRL-12 | Controller may **not** write `AGENTS.md` or `config.toml`. `propose_instruction` emits a diff to `.edgar/proposals/<id>.diff`, applied only by explicit `edgar controller apply <id>` | Must |
| CTRL-13 | `propose_skill` may target skill files only. It is applied directly only under `skills.synthesis = "auto"` and only inside `learned/` (SKL-11); every other case is a diff in `.edgar/proposals/` | Must |

### 7.10 Model routing

Rationale in [ADR-0013](adr/0013-model-routing.md). Three distinct mechanisms:
routing selects before the turn, escalation responds to capability failure,
fallback responds to unavailability.

| ID | Requirement | Priority |
|---|---|---|
| ROUTE-1 | Static role binding: separate models for main, controller, condenser, compactor, and per-subagent frontmatter | Must |
| ROUTE-2 | Declarative routing rules, first match wins, over a fixed condition set: `role`, `agent`, `mode`, `tools_required`, `prompt_tokens_lt/_gt`, `budget_remaining_lt`, `tags`, `schedule` | Must |
| ROUTE-3 | `select_model()` is a **pure function** of (context, rules, defaults) returning model, matched rule and reason | Must |
| ROUTE-4 | Routing costs no model call and adds no measurable latency | Must |
| ROUTE-5 | Escalation on deterministic failure triggers (tool-call errors, consecutive failures, schema violations); **upward only** along a declared chain; capped by `max_escalations` | Must |
| ROUTE-6 | Capability validation at selection time, not mid-turn: routing a tool-requiring task to a tool-incapable model is a hard error with a clear message | Must |
| ROUTE-7 | Fallback on provider unavailability (auth failure, sustained 5xx, exhausted backoff); targets must declare capabilities **at least equal** to the original. A target in a different adapter family runs with reasoning off for the rest of the turn (PRV-13) | Must |
| ROUTE-8 | Controller `switch_model` may only select from the escalation chain or a routing rule target, never an arbitrary model string | Must |
| ROUTE-9 | `edgar route explain` prints the selected model, matched rule and reason for a given context | Must |
| ROUTE-10 | Every escalation and fallback emits an event and is surfaced in the status bar; never silent | Must |
| ROUTE-11 | Budget-aware downgrade: a cap that would abort may instead route cheaper first, with a visible warning | Should |
| ROUTE-12 | `edgar route suggest` analyses experience telemetry and prints candidate rules with evidence. **Never writes config** | Should |

### 7.11 Scheduling

| ID | Requirement | Priority |
|---|---|---|
| SCH-1 | Declarative `schedules.toml`, hand-authored; `edgar schedule add` appends an entry from a template and never rewrites existing content | Must |
| SCH-2 | `edgar tick` computes what is due and runs it | Must |
| SCH-3 | `edgar install-tick` / `uninstall-tick` writes one host entry (cron, launchd, Task Scheduler) | Must |
| SCH-4 | Due calculation is a pure function of (schedules, last-run state, now) | Must |
| SCH-5 | Cron expressions plus interval shorthand (`@hourly`, `every 15m`) | Must |
| SCH-6 | Overlap prevention: a still-running schedule does not start again | Must |
| SCH-7 | Configurable catch-up policy after sleep: `skip`, `once`, `all` | Must |
| SCH-8 | Each entry carries its own mode, agent, model, tool allowlist and optional `verify` | Must |
| SCH-9 | Scheduled runs are non-interactive; transcripts written to `.edgar/runs/` | Must |
| SCH-10 | Per-entry `session_end` hook (EXT-5) for delivery | Must |
| SCH-11 | `schedule_self` tool with rate limits, max pending count and a self-scheduling depth guard; entries live in the `self_schedules` table of `edgar.db`, shown by `schedule list` tagged `[self]`, never in `schedules.toml` | Must |
| SCH-12 | `schedule list` / `add` / `remove` / `run <name>` for manual firing | Must |

### 7.12 Budget

| ID | Requirement | Priority |
|---|---|---|
| BUD-1 | Track tokens and cost per request, turn, session and subagent | Must |
| BUD-2 | Configurable caps at turn, session and daily level | Must |
| BUD-3 | Exceeding a cap aborts cleanly with exit 6 and a partial result where one exists | Must |
| BUD-4 | Subagent spend attributed to both the subagent and the parent session | Must |
| BUD-5 | Pricing table in config, overridable, with an explicit "unknown pricing" state rather than a wrong zero | Must |
| BUD-6 | `/cost` and `edgar cost` show current spend | Must |

### 7.13 Config and init

| ID | Requirement | Priority |
|---|---|---|
| CFG-1 | Layered: defaults < `~/.edgar/config.toml` < `./.edgar/config.toml` < env < CLI flags | Must |
| CFG-2 | `edgar config show --resolved` prints the effective config with the origin of every value | Must |
| CFG-3 | Schema-validated with actionable error messages naming the file, key and expected type | Must |
| CFG-4 | `edgar init` scaffolds project config, `AGENTS.md` stub and `.gitignore` fragment from templates, creating files and never overwriting existing ones | Must |
| CFG-5 | `edgar doctor` checks credentials, connectivity, MCP servers, extensions and their required commands, project trust, tick installation, DB integrity, and warns when `.edgar/` sits in a cloud-synced directory (iCloud Drive, OneDrive, Dropbox, Google Drive) | Must |
| CFG-6 | Secrets read from env, or from the OS keyring with the optional `keyring` extra; never written to a config file. A config naming a keyring secret without the extra fails with a hint | Must |
| CFG-7 | Config files are hand-authored; no automated component rewrites them. The controller may propose diffs | Must |
| CFG-8 | Config and instruction files are read once at session start. Changes take effect in the next session, and the REPL says so when a control file is edited mid-session | Must |

### 7.14 Verification

A turn is not done because the model says so. It is done when a declared check
passes. Rationale in [ADR-0014](adr/0014-verification-and-skill-synthesis.md).

| ID | Requirement | Priority |
|---|---|---|
| VER-1 | A verification command may be declared by `--verify` (CLI-17), a schedule entry (SCH-8), agent frontmatter (SUB-1), a loaded skill's frontmatter (SKL-1), or project config `verify.command`. The first source in that order wins; if the only sources are loaded skills, each of their commands runs, in load order | Must |
| VER-2 | The gate runs when the model ends a turn without tool calls, and only if the turn ran at least one non-read tool (`write`, `edit`, `shell`, custom, MCP). A read-only question never triggers a test run | Must |
| VER-3 | Exit 0 completes the turn. Non-zero returns the exit code and head/tail-truncated output (TOOL-4) to the model as a message tagged as verification feedback, and the loop continues. Capped by `verify.max_attempts`, default 2; each attempt charges the turn budget | Must |
| VER-4 | The command is authorised by `permissions.decide()` as a `shell` call **before the turn starts**. A non-interactive run whose verify command would need a prompt fails fast with exit 5 instead of doing the work and failing at the end. A `verify.command` from project config also requires project trust (PERM-13) | Must |
| VER-5 | Attempts exhausted: `-p` exits 9 with the last result still on stdout and `exit_reason: "verification_failed"` under `--json`; the REPL shows a warning and keeps the session | Must |
| VER-6 | Events `VerifyStarted(command, attempt)` and `VerifyFinished(ok, exit_code, attempt, duration_ms)`; the status line shows the check while it runs | Must |
| VER-7 | The result is recorded in experience telemetry (MEM-18) and is the signal that gates skill synthesis (SKL-8, SKL-11). A model-judged check is not a verification | Must |

### 7.15 Extensions, hooks and embedding

Rationale in [ADR-0018](adr/0018-extension-model.md). The vocabulary: a **tool** is
a function the model calls; a **skill** is instructions loaded on demand; an
**agent** is a subagent definition; a **hook** is a command run on a lifecycle
event; an **extension** is a folder bundling any of them.

| ID | Requirement | Priority |
|---|---|---|
| EXT-1 | An extension is a folder with `extension.toml` (`name`, `version`, `description`, optional `requires = { edgar, commands }`) and any of `tools/`, `skills/`, `agents/`, `hooks.toml`, `mcp.toml` | Must |
| EXT-2 | Discovered at `./.edgar/extensions/` and `~/.edgar/extensions/`; enabled by presence, disabled by `extensions.disabled`; project extensions are executable project config (PERM-13) | Must |
| EXT-3 | `edgar ext list`, `ext validate` (manifest schema, required commands on PATH) and `ext add PATH\|GIT_URL`, which copies the folder in and records source and commit in the manifest. No index, search or update service | Must |
| EXT-4 | Hooks declared as `[[hooks]]` with `event`, optional `match`, `command` (argv list) and `timeout_s`, in config or an extension's `hooks.toml` | Must |
| EXT-5 | Hook events: `session_start`, `pre_tool`, `post_tool`, `turn_end`, `verify_finished`, `session_end`. The hook receives the event as JSON on stdin | Must |
| EXT-6 | A `pre_tool` hook may only veto: exit 2 denies with stderr as the reason returned to the model; any other failure or timeout also denies (fail closed). Hooks cannot modify arguments or allow what policy denies | Must |
| EXT-7 | Hook output never enters the model's context or memory, except a `pre_tool` deny reason | Must |
| EXT-8 | Extension tools, skills and agents follow the same formats as their unbundled forms; their names take part in TOOL-9 collision order | Must |
| EXT-9 | `edgar.run(prompt, *, cwd, config, mode, model) -> TurnResult` is a documented async Python API over the same loop, stable from 1.0 | Must |
| EXT-10 | The formats in EXT-1 to EXT-9, TOOL-6, SKL-1, SUB-1, the `--json` and `--events` output and the `Provider`, `Sandbox` and `Retriever` protocols are frozen at 1.0 and change only additively within a major version | Must |
| EXT-11 | **Ports.** Core modules (`core/`, `context/`, `permissions/`, `tools/execute.py`) import no adapter, and adapters import only core types. Third-party implementations of the Provider, Sandbox and Retriever ports register through entry points, read lazily. One distribution ships the core and all built-in adapters ([ADR-0022](adr/0022-ports-and-adapters.md)) | Must |

## 8. Non-functional requirements

| ID | Requirement | Measure |
|---|---|---|
| NFR-1 | **Startup budget.** Time from process start to first byte of output for a trivial `-p` run with a fake provider | ≤ 150 ms on a 2020-era laptop; enforced by a CI test using `-X importtime` |
| NFR-2 | **Offline test suite runtime** | ≤ 60 s on CI |
| NFR-3 | **Core readability.** Lines of code in `core/` excluding tests | ≤ 2,000 |
| NFR-4 | **Total source size.** `src/` excluding tests, per tier ([ADR-0015](adr/0015-release-tiers.md)) | Core ≤ 5,000 LOC · v1.0 ≤ 8,000 · v2.0 ≤ 11,000 |
| NFR-5 | **Runtime dependencies**, counting optional extras ([ADR-0019](adr/0019-dependency-budget.md)) | ≤ 8 direct; currently 5 required + 1 optional, each justified in `docs/DEPENDENCIES.md` with its measured import cost |
| NFR-6 | **Platform parity.** Same test suite passes on Windows, macOS, Linux | Green CI matrix, no platform skips in core |
| NFR-7 | **Memory footprint** for a typical session | < 200 MB RSS |
| NFR-8 | **Test coverage** of `core/`, `tools/`, `permissions/`, `context/` | ≥ 90% branch |
| NFR-9 | **Type coverage** | `mypy --strict` clean on `src/` |
| NFR-10 | **Docs currency.** Every public command and config key documented | Enforced by a docs-coverage test |
| NFR-11 | **Cold install** from zero to first successful run | ≤ 2 minutes including reading the README |
| NFR-12 | **Tier isolation.** Core and v1 modules never import `edgar.controller`, `edgar.learning`, `edgar.schedule` or `edgar.providers.escalation` | An import-graph test, plus a CI job that deletes the v2 packages and runs the v1 suite green |
| NFR-13 | **Prompt budget.** Base system prompt, and the schemas of all Core built-in tools together | ≤ 1,500 and ≤ 2,500 tokens, measured in CI with the approximate counter |
| NFR-14 | **Supply chain.** How releases and dependencies are protected | Releases through trusted publishing with attestations; lockfile pinned with hashes; no install-time hooks; `SECURITY.md` and `/.well-known/security.txt` with a monitored contact from M0 |

## 9. Interface contracts

### 9.1 Command surface

```
Core
edgar                              interactive REPL (default)
edgar -p PROMPT [--mode M]         one-shot, non-interactive
edgar -p PROMPT --json             machine-readable single object
edgar -p PROMPT --events           event stream as JSON Lines
edgar -p PROMPT --verify CMD       done only when CMD exits 0
edgar -p PROMPT --plan             plan only, read-only; the plan is pinned
edgar -p PROMPT --show-thinking    render reasoning where the provider exposes it
edgar --resume [ID] | --continue   restore a session
edgar trust [--yes]                trust this project's executable config
edgar prompt show                  print the effective system prompt and its token count
edgar models list
edgar tools list | describe NAME
edgar skills list | validate
edgar permissions list | revoke ID
edgar context show
edgar sessions list | show ID | rm ID
edgar cost

v1.0
edgar --fork ID[@TURN]             branch a session at a turn
edgar init                         scaffold project config
edgar doctor [--network]           diagnose environment; list every reachable host
edgar config show [--resolved]
edgar agents list | validate
edgar mcp list | test SERVER
edgar ext list | validate | add PATH|GIT_URL
edgar route explain [--agent A] [--mode M] [--tokens N]
edgar memory list | add TEXT | edit | review | forget ID | undo
edgar sessions compact ID

v2.0
edgar skills list --learned | distill NAME | curate | forget NAME
edgar route suggest                analyse telemetry, print candidate rules
edgar history show | distill
edgar stats
edgar schedule list | add | remove | run NAME
edgar tick
edgar install-tick | uninstall-tick
edgar controller log | revert ID | apply ID
```

### 9.2 Stream discipline

| Stream | Carries |
|---|---|
| stdout | The result only. Model text in interactive and `-p`, a JSON object under `--json`. Never ANSI when not a TTY. |
| stderr | Status line, permission prompts, warnings, logs, errors. |

Status line renders only when `stderr.isatty()` and `--quiet` is absent and
`NO_COLOR`-style suppression does not apply.

### 9.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Generic runtime error |
| 2 | Usage error (bad flags, no TTY and no `-p`) |
| 3 | Config error (invalid config, missing required `--mode` when piped) |
| 4 | Provider error (auth, network, rate limit exhausted) |
| 5 | Permission denied |
| 6 | Budget exceeded |
| 7 | Cancelled by user |
| 8 | Tool failure the agent could not recover from |
| 9 | Verification failed after `verify.max_attempts` (VER-5) |

`ContextOverflow` (CTX-12) exits 1 with a hint. An untrusted project with
executable config in a non-interactive run exits 3 (PERM-13).

### 9.4 `--json` output shape

```json
{
  "ok": true,
  "result": "…model output…",
  "session_id": "01J…",
  "model": "openai/gpt-5",
  "usage": { "input_tokens": 1200, "output_tokens": 340, "cached_tokens": 800 },
  "cost": { "amount": 0.0142, "currency": "USD", "approximate": false },
  "tools_used": [{ "name": "read", "count": 3 }],
  "subagents": [{ "name": "explorer", "model": "ollama/qwen3", "cost": 0.0 }],
  "verification": { "status": "passed", "command": "just check", "attempts": 1 },
  "exit_reason": "completed",
  "warnings": []
}
```

### 9.5 On-disk layout

```
~/.edgar/                     user scope
  config.toml                 hand-authored
  AGENTS.md                   hand-authored, optional user-scope instructions
  agents/  skills/  tools/  extensions/
  edgar.db                    machine-owned: project trust, user-scope facts
  logs/

./.edgar/                     project scope (created by `edgar init` or by hand)
  config.toml                 hand-authored
  agents/  skills/  tools/  extensions/
  skills/learned/             machine-owned: synthesised skills (SKL-11, v2)
  proposals/                  machine-owned: diffs awaiting `controller apply` (v2)
  schedules.toml              hand-authored; `schedule add` appends (v2)
  sessions/<id>.jsonl         machine-owned: append-only transcripts
  sessions/<id>/blobs/        machine-owned: spilled tool output (CTX-13)
  runs/                       machine-owned: scheduled run transcripts (v2)
  edgar.db                    machine-owned: sessions index, grants, facts,
                              self-schedules, telemetry, control-file hashes
  history.md                  machine-owned (v2)

./AGENTS.md                   hand-authored instructions, never machine-written
```

**Ownership.** Automated writers (the loop, learner, controller, synthesiser,
tools acting on the model's behalf) may write only to `edgar.db`, `history.md` and
per-skill `HISTORY.md`, `sessions/`, `runs/`, `proposals/` and `skills/learned/`.
Everything else under `.edgar/` and `~/.edgar/`, plus the instruction files, is
hand-authored (MEM-2). Human-invoked commands (`init`, `schedule add`, `ext add`)
may create files or append from templates, and never rewrite existing content. The
model's own `write` and `edit` calls on control files always go through a prompt
(PERM-12).

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Startup latency creeps past the NFR as features land | Kills the piping story | CI test on import time from milestone 1, before there is anything to regress |
| Scope creep from "wouldn't it be nice" | Project never ships, teaching value drowns | Non-goals table in §5.2 is normative; changes need an ADR |
| Provider API drift breaks adapters silently | Users hit it before CI does | Scheduled live smoke tests that open an issue on failure |
| Compaction bug corrupts transcripts | Data loss, unrecoverable sessions | Pairing invariants as property tests; compaction writes a new revision rather than mutating |
| Controller causes unexplainable config drift | Loss of trust in the tool | Whitelist, dry-run, full mutation log, revert, tighten-only |
| Autolearn poisoned via injected content | Persistent compromise across sessions | Only typed text and harness-computed error records create active facts (MEM-8/9/22); model-proposed and distilled facts stay pending until a human confirms (MEM-17/21) |
| A cloned repository ships hooks, MCP servers or tools that run on launch | Arbitrary code execution from `git clone && edgar` | Project trust keyed by a hash of executable config (PERM-13); non-interactive untrusted runs exit 3 |
| `auto` mode reads a page with injected instructions and exfiltrates data | Data leaves the machine | Taint tightens `auto` defaults for shell and network egress after untrusted content arrives (PERM-11); the docs recommend a container for untrusted work |
| The agent edits its own config to widen its policy | Silent privilege growth | Control files are always-ask and read once per session (PERM-12, CFG-8); grants live in the DB, not in config (PERM-6) |
| Scope grows past "lightweight" | Unreadable codebase, never ships | Per-tier size budgets (NFR-4) and a removable v2 (NFR-12) |
| A dependency or release is compromised (as LiteLLM's was in 2026) | Malware on users' machines | Five required dependencies, hash-pinned lockfile, trusted publishing with attestations, one distribution to secure (NFR-5, NFR-14, ADR-0022) |
| A default quietly sends prompts to a host the user never chose | Broken trust, data leaves the machine | No implicit models or hosts, auxiliary roles default to the main model, `doctor --network` (PRV-15) |
| A synthesised skill carries a wrong procedure or an injected instruction | Future sessions follow it as instructions | Synthesiser never sees tool output (SKL-9); `auto` needs a passing verification (SKL-11) and is opt-in with a disclaimer (SKL-13); writes confined to `learned/`, each one revertible (SKL-12) |
| Verification is declared once and runs on every turn | Slow sessions, wasted spend | Gate runs only after turns that ran a non-read tool (VER-2); attempts capped (VER-3) |
| A secret lands in a committed `history.md` | Credential leak | Redaction on write, gitignored by default (OQ-1), `--no-history` |
| Windows behaves differently and gets neglected | Half the audience has a broken tool | Windows in the CI matrix from milestone 1; no platform skips permitted in core |
| Runaway subagent recursion burns money | Real financial cost | Depth ceiling, recursion guard, inherited budgets, hard caps |
| Docs drift from code | Teaching value collapses | Docs-coverage test; examples executed in CI |

## 11. Success criteria

**Core (0.x) ships when:**

- Every Must requirement mapped to Core in §5.1 is implemented and tested
- CI green on Windows, macOS and Linux; NFR-1, NFR-2, NFR-3, NFR-6 met; `src/` ≤ 5,000 LOC
- J2, J3 and J9 pass their acceptance tests
- A user adds a command tool and an HTTP tool from the docs without opening `src/`

**v1.0 ships when:**

- All Must requirements mapped to Core and v1 are implemented and tested
- CI green on Windows, macOS and Linux
- NFR-1 through NFR-6 measurably met
- A developer unfamiliar with the codebase can add a provider in under an hour
  using only `docs/`, verified by trying it on someone
- A non-Python user can add a custom tool, a subagent, a skill and an extension
  without opening `src/`
- The guided tour walks a reader from "what is a turn" to "here is the loop" with
  runnable code at each step
- The formats listed in EXT-10 are documented as stable

**v2.0 ships when:** all Must requirements are met, `src/` ≤ 11,000 LOC, J5 to J8
pass, and NFR-12 holds (v1 suite green with v2 deleted).

**Health signals after ship:** issues that are questions rather than bug reports;
forks that modify rather than merely star; a provider or tool contributed by
someone who is not Diego.

## 12. Open questions

Tracked here rather than silently decided. Each needs resolving before or during
the milestone that depends on it.

| ID | Question | Lean | Blocks |
|---|---|---|---|
| OQ-1 | `history.md` committed or gitignored by default? | Gitignored, documented opt-in | M12 |
| OQ-3 | Exact per-provider tokenisers or one approximate with correction factors? | Approximate + correction, exact where usage is returned | M2 |
| OQ-6 | What counts as "the same task shape" for the repeat trigger (SKL-8d)? | A hash of agent, the ordered set of distinct tool names, and routing tags. Visible, and cheap to compute, but blind to intent. Revisit if it misfires on real telemetry | M14 |
| OQ-7 | Taint scope: sticky for the session, or cleared when the untrusted result is compacted away? | Sticky per session. A summary can carry injected text forward, and per-turn clearing is hard to explain ([ADR-0021](adr/0021-humans-widen-machines-tighten.md)) | M3 |
| OQ-8 | When does the OpenAI Responses API adapter land? | When the eval set shows the reasoning gap matters on tool-heavy tasks; v2 at the latest ([ADR-0020](adr/0020-provider-portability.md)) | M15 |
| OQ-9 | Does `ext add` from a git URL need an `ext update`? | No command in v1: re-run `ext add` over the folder, and the manifest records the new commit. Revisit if people ask | M10 |

**Resolved:**

| ID | Question | Resolution |
|---|---|---|
| OQ-2 | May the controller ever touch `AGENTS.md`? | **No.** `AGENTS.md` is part of what constrains the controller; letting it edit its own constraints is a loop with no fixed point and it fails silently. `propose_instruction` emits a diff the human applies. [CTRL-12, ADR-0008] |
| OQ-4 | Full TUI or line-oriented with a status line? | **Line-oriented.** The field review found flicker, broken scrollback and unselectable text among the most common TUI complaints; output stays in native scrollback (CLI-23) |
| OQ-5 | Session storage: pure SQLite or JSONL transcript + DB indices? | **JSONL + DB**, because a greppable transcript is worth a lot in a teaching repo. Compaction appends records rather than rewriting. [ADR-0010, ADR-0016] |
