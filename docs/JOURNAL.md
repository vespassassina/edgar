# Journal

What was asked, what was done, what was decided and what is still open, newest
first. Decisions with alternatives worth keeping get an ADR; user-visible changes
also go in [`CHANGELOG.md`](../CHANGELOG.md); milestone state is the table at the
top of [`ROADMAP.md`](ROADMAP.md).

## Open items

Carried forward until done. Newest first.

- **Try the REPL on a real model.** Start Ollama (`OLLAMA_CONTEXT_LENGTH=16384
  ollama serve`), then `uv run edgar --model ollama/qwen3:8b` from the repo. M4 was
  tested with the fake model and through a pseudo-terminal, not live.
- **`@path` attachments in prompts** (CLI-3) are not built; piped stdin is. Pick a
  milestone for them (M5 is the natural one).
- **Release M1, M2 and M4?** Nothing since 0.0.2 is on PyPI. An interim release would be
  0.0.3; the roadmap keeps 0.1 for the Core release (M6). Waiting on the maintainer.
- **Record the remaining cassettes** with real keys: `just record-cassettes openai`
  (and azure, openrouter, anthropic). Only Ollama's are recorded so far.
- **Apply the `AGENTS.md` patch.** It is hand-authored, so the maintainer applies it:
  `patch -p1 < …/scratchpad/AGENTS.md.patch` (ADR-0007). It still lists `pydantic` in
  the startup import ban.
- **Live smoke workflow** (TESTING.md layer 5) is specified but not created; it
  needs provider secrets in the repository settings first.
- **Size watch.** Core is at 4,299 of 5,000 after the review; M5 should take about
  450 lines and M6 about 200. Next candidates to move if needed: `/history`, then
  `edgar context show` (ADR-0037).
- Update the GitHub repository description to the headline (optional).

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
