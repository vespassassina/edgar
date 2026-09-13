# Journal

What was asked, what was done, what was decided and what is still open, newest
first. Decisions with alternatives worth keeping get an ADR; user-visible changes
also go in [`CHANGELOG.md`](../CHANGELOG.md); milestone state is the table at the
top of [`ROADMAP.md`](ROADMAP.md).

## Open items

Carried forward until done. Newest first.

- **Stop the local Ollama server when done testing.** It runs as `ollama serve` in a
  terminal (not as a brew service): Ctrl-C there, or `pkill -x ollama`.
- **Release M1 and M2?** Nothing since 0.0.2 is on PyPI. An interim release would be
  0.0.3; the roadmap keeps 0.1 for the Core release (M6). Waiting on the maintainer.
- **Record the remaining cassettes** with real keys: `just record-cassettes openai`
  (and azure, openrouter, anthropic). Only Ollama's are recorded so far.
- **Apply the `AGENTS.md` patch.** It is hand-authored, so the maintainer applies it:
  `patch -p1 < …/scratchpad/AGENTS.md.patch` (ADR-0007). It still lists `pydantic` in
  the startup import ban.
- **Live smoke workflow** (TESTING.md layer 5) is specified but not created; it
  needs provider secrets in the repository settings first.
- **Size watch.** Core is at 2,409 of 5,000 lines after M2, with M3 to M6 still
  to build. M4 and M3 need to stay lean.
- Update the GitHub repository description to the headline (optional).

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
