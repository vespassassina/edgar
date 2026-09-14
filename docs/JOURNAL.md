# Journal

What was asked, what was done, what was decided and what is still open, newest
first. Decisions with alternatives worth keeping get an ADR; user-visible changes
also go in [`CHANGELOG.md`](../CHANGELOG.md); milestone state is the table at the
top of [`ROADMAP.md`](ROADMAP.md).

## Open items

Carried forward until done. Newest first.

- **Review the capability broker design** (ADR-0039, M17) before M17 starts. The
  choices most open to argument: five caveats only; caveats only from what people
  type (no model-derived scope); no prompt on a refusal, `/scope` widens; the log
  named "receipt"; HMAC and its limit; on by default in v2; M17 before M16; about
  400 lines against v2's budget.
- **Try the REPL on a real model.** Start Ollama (`OLLAMA_CONTEXT_LENGTH=16384
  ollama serve`), then `uv run edgar --model ollama/qwen3:8b` from the repo. M4 was
  tested with the fake model and through a pseudo-terminal, not live.
- **`@path` attachments in prompts** (CLI-3) are not built; piped stdin is. M5 did
  not take them (no lines to spare); pick a milestone.
- **Release M1 to M5?** Nothing since 0.0.2 is on PyPI. An interim release would be
  0.0.3; the roadmap keeps 0.1 for the Core release (M6). Waiting on the maintainer.
- **Record the remaining cassettes** with real keys: `just record-cassettes openai`
  (and azure, openrouter, anthropic). Only Ollama's are recorded so far.
- **Live smoke workflow** (TESTING.md layer 5) is specified but not created; it
  needs provider secrets in the repository settings first.
- **Size watch.** Core is at 4,825 of 5,000 lines of code after the loop's
  refactor; M6 has about 175. Next
  candidates to move if needed: `/sessions`, then the personality warning
  (ADR-0038).
- **Which style guide?** The sensible-defaults rule went into PRD §4, CLAUDE.md and
  the `AGENTS.md` patch. If "my style guide" meant another file, name it.

## 2026-09-14 · The tour in artifactkit, on a midnight theme

**Asked**
- The tour must be HTML, published on GitHub as HTML, and linked from the repo's
  docs so a reader can just click. Use the maintainer's HTML style guide, with a
  dark, desaturated midnight-blue background.

**Done**
- Restyled `docs/tour/index.html` with artifactkit (the maintainer's kit): page
  head, sticky contents, section heads with status pills, stops as exhibits, a
  stepper for the five stages that marks a stage done when its stops are read, the
  size table as an `ak-table` with its source line, print rules. The three
  stylesheets are vendored in `docs/tour/artifactkit/`; only the theme block differs
  (`--t-bg:#121826`). Mermaid is themed from the same tokens and loads as the UMD
  build.
- Fixed a rendering bug: Mermaid read the turn diagram's "1. record the prompt"
  labels as Markdown lists and drew "Unsupported markdown: list". Steps are now
  written "1 · …"; `test_tour.py` checks for it and that the page's own files exist.
- Every doc link to the tour now opens the published page
  (<https://vespassassina.github.io/edgar/>), not the HTML source: README (a line
  under the headline, plus the Documentation table), BLUEPRINT, ROADMAP, TESTING and
  CLAUDE.md. The repository description ends with "Take the tour" and the address.
- ADR-0040 amended.
- The maintainer applied `docs/proposals/AGENTS.md.patch` by hand during this
  session; it went out in this commit, and the patch file and `docs/proposals/` are
  removed. CLAUDE.md and ADR-0040 no longer call it pending.

**Decided**
- The kit's stylesheets are linked, not inlined: it is a hosted page, and the
  source stays readable. artifactkit's single-file validator therefore reports the
  linked files, the Mermaid script and the raw storage keys; accepted for Pages.

## 2026-09-14 · Written to be read, and A Tour of the Harness

**Asked**
- Add granular comments, close to pseudocode, to `core/loop.py`, `core/message.py`
  and `core/events.py`. From now on, add them to any code file touched. Prefer
  shallow functions and avoid recursion.
- "Lines" always means lines of code, and comments do not count: the 5,000 limit is
  Core's code without comments. Say so in the docs and the checks.
- Write a step-by-step reading guide, a tour of the harness, with diagrams and
  sections that point at the files on GitHub, and keep it in sync. Base it on the
  maintainer's own reading guide (`OneDrive/Writing/projects/edgar/`).
- Make it HTML, split into Core, v1 and v2 so it can be read a tier at a time,
  publish it on GitHub, link it from the repository's description, and call it "A
  Tour of the Harness".
- Add to the docs and the style guide: always propose sensible defaults (Enter
  accepts about 90% of the time) and preconfigured config files when installing and
  deploying.

**Done**
- `core/loop.py`: a pseudocode header, and `run_turn` as ten numbered steps over
  five shallow helpers and a `_Turn` dataclass. Behaviour is unchanged. `core/message.py`
  and `core/events.py`: an example transcript, the pairing rule, the bus diagram,
  the order of a turn's events, and who emits each event.
- `tests/support/budget.py`: the loop counted in lines of code like everything
  else; `broker` added to the v2 paths. Budget tests rewritten: comments in the loop
  are free, code is not.
- [ADR-0040](adr/0040-written-to-be-read.md). PRD §4 gains principles 11 (sensible
  defaults) and 12 (written to be read); NFR-3 and NFR-4 define a line of code.
  README, BLUEPRINT, TESTING, ROADMAP and CLAUDE.md say "lines of code".
- [A Tour of the Harness](tour/index.html): 18 built stops in five stages, the M6
  skills stop, five v1 stops and six v2 stops marked planned with their milestone.
  Five diagrams, checked against the code: the layer map, the turn (numbered like
  `run_turn`), the bus, the tool pipeline, the permission decision and compaction,
  plus one showing where v1 plugs in and one showing where v2 attaches. A per-reader
  "read" box and a reading clock, kept in the browser.
  `.github/workflows/tour.yml` publishes it to <https://vespassassina.github.io/edgar/>;
  the repository's website link points there. `tests/unit/test_tour.py` keeps it
  honest.
- The `AGENTS.md` patch moved into the repository, at
  `docs/proposals/AGENTS.md.patch`, and gained the new comment, function and
  defaults rules, "LOC" for the loop, and `edgar.broker` in tier isolation.

**Decided**
- Every limit is lines of code; the loop's physical-line limit is gone (ADR-0040).
- Narration goes in `#` comments, not docstrings, because docstrings count.
- The tour is hand-written HTML with fixed hooks a test reads, not a generated
  file. It replaces the planned `docs/TOUR.md` (M11).
- Diagrams corrected against the code: a denied, invalid or unknown call still ends
  as a `ToolResultBlock`; `decide` checks yolo right after catastrophic commands and
  before credential paths; an `Ask` with nobody to answer becomes a `Deny` with
  `needed_prompt`.
- Left out of the tour from the maintainer's guide: the article, the broker
  decision notes and the reading log, which are personal.

**Pending**
- The shallow-helper split cost 19 lines of Core; M6 has about 175.
- ~~Apply `docs/proposals/AGENTS.md.patch`.~~ Applied by the maintainer the same day.

## 2026-09-14 · Capability broker added to v2 (spec only)

**Asked:** add to the features the capability broker we had been discussing, for
v2. The notes were the maintainer's prototype in
`OneDrive/ClaudeCode/capability-broker/` (0.0.1, 2026-09-02: intent, capability
and provenance, the ceiling and the ticket, eleven invariants, five open
questions).

**Done**
- [ADR-0039](adr/0039-capability-broker.md): the prototype mapped onto edgar.
- PRD: a v2 scope bullet, a `Broker` row in the requirement map, §7.16 with
  CAP-1..10, `/scope` and `--scope` in the CLI row, `edgar receipt` in §9.1,
  `receipt.jsonl` and `~/.edgar/receipt.key` in §9.5, `edgar.broker` in NFR-12.
- Blueprint: `broker/` in §1 and §2, `ScopeRefused` in §3.2, the `pre_tool` stage
  as hooks plus in-process vetoes in §6.2 and §6.7, a new §7.6, notes in §9 and
  §12.
- Roadmap: eighteen milestones, v2 is M12–M17, a new M17 built after M15 and before
  M16; M16 gains scheduled-run tickets.
- TESTING.md: broker property tests; `edgar.broker` in the tier-isolation list, and
  in `tests/unit/test_architecture.py` so the rule already holds. README and
  CLAUDE.md follow.

**Decided** (all in ADR-0039)
- Enforce in the tool pipeline, not with bound handles: tool schemas sit above the
  cache breakpoint and cannot change per task (CTX-17).
- Intents only from typed text, the MEM-8 source; subagent tasks, `/steer` and
  `schedule_self` refine an intent and never start one. That answers the
  prototype's "injected intent" question.
- Five caveats (`tools`, `paths`, `hosts`, `calls`, `until`); `shell` refused under
  a `paths` or `hosts` scope unless named.
- A veto only, never a prompt; the human widens with `/scope`.
- The signed log is called the receipt, since "provenance" already names config
  and fact origins. HMAC-SHA256 with a user-only key: tamper-evident against the
  agent, not against the user.
- No daemon, service, policy language or Ed25519: the Never list and NFR-5.

**Pending:** the maintainer's review of the design (open items). No code for the
broker until M17.

## 2026-09-13 · M5 done: context and sessions

**Asked:** start M5.

**Done**
- `storage/transcript.py`: the JSONL record in `.edgar/sessions/` (git-ignored),
  replay, `find` by id or unique prefix, the listing. `--resume [ID]`,
  `--continue`, `edgar sessions list|show|rm`.
- `context/compact.py`: S1 elide, S2 fold into one summary (the compactor model,
  or the main one), S3 only past the window, `ContextOverflow` with a hint; every
  stage recorded and replayed by position. Runs before every request, so it
  compacts inside a long tool-calling turn too. `/compact [FOCUS]`.
- `context/builder.py`: personality and instruction files (project, then
  `~/.edgar/`) read once and joined to the system prompt; `edgar prompt show`
  includes the personality.
- Session commands `/new /clear /reset /undo [N] /retry /title /sessions /load ID`,
  each an appended record. The REPL prints the conversation on resume.
- Turn and session cost caps: reason `budget_exceeded`, `-p` exits 6.
- The control-file check: digests at session start and end, a `control` record,
  a warning in the next session.
- Tests: a 200-turn session on a 6,000-token window compacts over and over (mostly
  S1), with the pairing invariant and an unchanged prefix on every request, and
  replays to the exact view; a 40-call turn compacts inside itself; overflow;
  caps; resume; `/undo 2` then replay; property tests for every stage. 419 tests
  in about 6 s.

**Decided**
- [ADR-0038](adr/0038-context-and-sessions-as-built.md): records address the view
  by position (`upto`); S3 only past the window, and CTX-8 reworded to match; the
  output reserve is at most half the window; a cap is a turn reason, not an
  exception, and unknown price counts as over; the control check compares within
  a session; block kinds are class names.
- Size: M5 as specified left 126 lines for M6. Collapsing trailing-comma splits gave
  17; `/history` and `edgar cost` moved to M7, `edgar context show` to M11.
  Core 4,806.
- CTX-10 (`edgar sessions compact`, a Should) not built; it stays in M11.

**Next:** M6, skills and the Core release (0.1, ask first).

## 2026-09-13 · Review for size; four features to v1

**Asked:** a quick review to shave and simplify, then follow the recommendation;
"core stays core, 5k limit".

**Done**
- Review: Anthropic became a row in the quirks table, with one `connect()` for
  endpoint and key checks (both adapters lost their `make()`); the fake
  provider's scripting moved to `tests/support/scripted.py`; `read` and `ls` use
  the shared schema helper. 116 lines out, 4,415 → 4,299, all 388 tests green.
- Moved to v1: plan mode and `todo` (M9), `/save` `/load` `edgar --load` and the
  daily cost cap (M7), `edgar login` (M8, with MCP OAuth).

**Decided**
- [ADR-0037](adr/0037-core-fits-in-5000.md): Core stays under 5,000 lines;
  simplify first, then move whole features.

**Next:** M5.

## 2026-09-13 · M3 done: tools, permissions, the verify gate

**Asked:** start M3.

**Done**
- `permissions/`: a pure `decide()` over a `Policy`, the mode table from the
  Blueprint cell by cell, rules, exact grants in `.edgar/edgar.db`, taint, control
  files, credentials, and hostile paths resolved before matching. The guard asks
  in the REPL (answer with the next line: once, session, always, no) and denies
  with `-p`, which then exits 5. 100% branch coverage.
- Built-ins `write`, `edit`, `glob`, `grep`, `shell`, `fetch`; processes are killed
  as a group on cancel or timeout.
- Command and HTTP tools from `.edgar/tools/*.toml` and `~/.edgar/tools/`,
  project over user over built-in with a warning; project trust with
  `edgar trust` and `--no-project-exec`.
- The verify gate (`--verify`, `[verify] command`): authorised before the turn,
  run when the model stops after a non-read tool, feedback on failure, exit 9
  when exhausted.
- yolo only through `EDGAR_YOLO=1` or a typed confirmation.
- 388 tests in about 5.5 s.

**Decided**
- [ADR-0036](adr/0036-safety-layer-as-built.md): outside the working directory
  asks rather than denies; the audit trail is the event stream until M5; `/browser`
  moves to M8 and the control-file hash warning to M5.

**Budget.** M3 took about 1,060 lines against a target of 800. Core is at 4,415 of
5,000, with 585 left for M5 (context, compaction, sessions, session commands,
personality, cost caps, plan and todo) and M6 (skills, `edgar login`, release).
They will not both fit. Candidates for v1, by how separable they are: `/save` and
`/load` with `edgar --load`; plan mode and the `todo` tool; the daily cost cap;
`edgar login`; skills. Alternatively the Core budget is raised by an ADR, which
the roadmap says it should not be.

**Next:** the maintainer decides what moves; then M5.

## 2026-09-13 · M4 done: the REPL

**Asked:** start M4 (the interactive shell and model picker, per the replan).

**Done**
- `edgar` on a terminal opens the REPL: a prompt that stays open while a turn runs,
  text streamed a line at a time above it, and the status line as its toolbar.
  Plain text queues, `/steer` lands at the loop's safe point, `/btw` answers on the
  side without touching the transcript, `/stop` and Ctrl-C cancel (twice exits),
  `/pause` and `/resume` hold at the safe point. Also `/status /model /mode
  /thinking /queue /cost /title /new /clear /help /quit`; commands that need later
  milestones say which.
- Cancellation seals the transcript (`core/cancel.py`): unanswered calls get
  "cancelled by user", streamed text is kept marked interrupted. A property test
  cancels at generated moments and checks the pairing invariant every time.
- `edgar models` and `/model` pick a provider, then one of its models, fetched
  from that provider only when asked; `edgar models` writes the default into a new
  config file, never an existing one.
- `-p`: `--json`, `--events`, `--quiet`, `--show-thinking`, `--no-color`; piped
  stdin attached as context; a status line on stderr; Ctrl-C exits 7.
- 329 tests in about 4.5 s. The REPL was also driven through a pseudo-terminal
  against the fake model.

**Decided**
- [ADR-0035](adr/0035-repl-as-built.md): prompt_toolkit owns the bottom of the
  screen, text streams a line at a time, no Markdown rendering, and `rich` is
  dropped from the dependencies; the REPL's logic is a plain `Shell` class.

**Next:** M3, tools, permissions, the verify gate, and CLI/HTTP tools.

## 2026-09-13 · M2 done; first real model; replan

**Asked**
- Start M2 (real providers).
- "I don't have credits on the Anthropic API key. Can we use my subscription?"
- edgar works on Ollama; how to stop Ollama.
- Plan for OAuth; an interactive shell; an edgar model picker for choosing and
  configuring models; keep track of everything we do.
- "We need API + CLI soon; 3,000 tokens for the MCP is too much."

**Done**
- M2, commit `ff4db71`: `openai_compat.py` with the quirks table (OpenAI, Azure,
  OpenRouter, Ollama, any `[providers.NAME]`), `anthropic.py`, shared `http.py`
  (retries, SSE, error mapping, token counts), `repair.py`, `pricing.py`,
  `routing.py`, prompt profiles with `compact.md`, `[providers.*]` and
  `[pricing.*]` config, `edgar models list`. CI green on all nine jobs.
- Contract suite over six providers (offline in about 2 s), a loopback fixture
  server for user-defined providers, cassette record and replay, 290 tests in
  total.
- **First live model run:** the Ollama contract suite passed live against
  `qwen3:8b` on the maintainer's Mac (15 recordable tests), and Ollama's cassettes
  are now recorded exchanges rather than synthetic ones. Recording found a flaw:
  tests sharing a scenario overwrote each other's recording. Fixed: the first test
  to use a scenario owns its recording.
- Subscriptions answered: not possible, by Anthropic's terms and by edgar's own
  recorded decision. Free ways to test were given instead: Ollama (used), OpenRouter
  `:free` models, Gemini's free tier through a config block.
- Tracking started: this journal, `CHANGELOG.md`, a status table in the roadmap,
  and the rule in `CLAUDE.md`.

**Decided** (the maintainer chose each, 2026-09-13)
- [ADR-0031](adr/0031-provider-layer-as-built.md): how the provider layer was
  built where the Blueprint sketch left room: tool support learned from the first
  refusal, no reasoning replay over Chat Completions, synthetic cassettes until
  recorded, OQ-3 resolved.
- [ADR-0032](adr/0032-oauth-keys-and-mcp.md): OAuth only to issue API keys
  (`edgar login`, OpenRouter first, M6) and for remote MCP servers (moved from v2 to
  M8). Never for subscriptions, now also a PRD non-goal.
- [ADR-0033](adr/0033-replan-after-m2.md): M4 (the REPL) comes next, before M3.
  Command tools and HTTP tools (the "CLI + API" alternative to MCP) move from M6
  to M3 along with project trust; `/browser` can point at a browser CLI.
- [ADR-0034](adr/0034-model-picker.md): `edgar models` and `/model` become an
  interactive picker that lists a provider's models only on request, and creates
  a config but never edits one.

**Next:** M4, the REPL.

## 2026-09-13 · M0 and M1; spec additions

**Asked**
- Start building Core; connect the GitHub repository; choose a licence; publish to
  PyPI.
- What the invariant is; a block diagram in the README.
- Input during a turn: `/queue` (the default), `/steer`, `/btw`.
- Session commands: `/new /reset /clear /history /save /retry /undo N /title /stop
  /pause /resume /plan /status /sessions /model /init /load /browser`, and a
  `personality.md` file.

**Done**
- M0: the package skeleton, CI on {ubuntu, macos, windows} × {3.12, 3.13},
  trusted publishing. Released as `edgar-harness` 0.0.1 and 0.0.2 (0.0.2 adds the
  `edgar-harness` command so `uvx edgar-harness` works).
- M1, commit `2c25162`: messages and the pairing invariant, the event bus, the
  loop, the fake provider, `read` and `ls`, the tool pipeline with spill, the
  deny-by-default policy, the prompt file, layered config with provenance.
- The README block diagram; spec updates for input during a turn, session commands
  and the personality file (commit `c6ec5a1`).

**Decided**
- [ADR-0026](adr/0026-licence-agpl.md): AGPL-3.0-or-later.
- [ADR-0027](adr/0027-distribution-name.md): distributed as `edgar-harness`
  (the name `edgar` was taken on PyPI); the command stays `edgar`.
- [ADR-0028](adr/0028-input-during-a-turn.md): plain text queues, `/steer` lands at
  the loop's one safe point, `/btw` runs outside the transcript.
- [ADR-0029](adr/0029-session-commands.md): session commands append records and
  never rewrite; `/undo` rewinds the conversation, not the disk (OQ-10); titles
  never use a model.
- [ADR-0030](adr/0030-personality-file.md): `personality.md`, the project file
  replacing the user one; tone only, never permissions.
