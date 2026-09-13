# Changelog

What changed for people using edgar, newest first. The reasons live in
[`docs/adr/`](docs/adr/), the day-by-day record in [`docs/JOURNAL.md`](docs/JOURNAL.md).
Versions follow the tiers in [`docs/ROADMAP.md`](docs/ROADMAP.md): 0.0.x while
Core is being built, 0.1 at the Core release (M6).

## Unreleased

### Added
- `edgar -p PROMPT` runs one turn (M1): the turn loop, the `read` and `ls` tools,
  deny-by-default permissions (reads inside the working directory only), the
  system prompt as a file (`edgar prompt show`), and layered config with
  provenance and error messages that name the file, the key and the expected type.
- Real providers (M2): `openai/…`, `azure/…`, `openrouter/…`, `ollama/…`,
  `anthropic/…`, and any OpenAI-compatible server as a `[providers.NAME]` block.
  Keys come from the environment only; a missing key fails before any request.
- Retries with backoff on 429 and 5xx, honouring `Retry-After`.
- Deterministic repair of malformed tool calls from small models (code fences,
  trailing text, JSON written as text); `native_tools = false` for servers with no
  tool support.
- Cost per request: a small dated price table, `[pricing."provider/model"]`
  overrides, provider-reported cost for OpenRouter, zero for Ollama, and "unknown"
  instead of a wrong zero for everything else.
- `edgar models list`: where each role's prompts go and whether each provider's
  key is set, without contacting anything.
- A compact system prompt for models with under 32k tokens of context.
- The interactive REPL (M4): `edgar` on a terminal. Keep typing while it works:
  plain text queues the next prompt, `/steer` corrects the turn in flight, `/btw`
  asks a side question without touching the conversation. `/stop` or Ctrl-C
  cancels (twice exits), `/pause` and `/resume`, `/status`, `/cost`, `/mode`,
  `/thinking`, `/title`, `/new`, `/clear`, `/help`. A status line under the prompt.
- `edgar models` and `/model`: pick a provider and one of its models; the default
  goes into a new config file, never into an existing one.
- Writing and running (M3): `write`, `edit`, `glob`, `grep`, `shell` (Git Bash,
  PowerShell or your POSIX shell) and `fetch`.
- Permissions: four modes, `[permissions]` rules per tool, `write_paths`,
  `shell_allow` and `shell_deny`; in the REPL, answer once, for the session, or
  always (stored as a grant; `edgar permissions list|revoke`). Anything outside
  the working directory asks; credentials are off limits; writing edgar's own
  config and instruction files always asks. After reading web content, `auto`
  asks before the shell or the network. `-p` exits 5 when a call needed a prompt.
  yolo needs `EDGAR_YOLO=1` or the word typed.
- The verify gate: `--verify CMD` or `[verify] command` runs your check when the
  model stops after changing something; failures go back to the model, and `-p`
  exits 9 when the attempts run out.
- Command tools and HTTP tools in `.edgar/tools/*.toml` and `~/.edgar/tools/`: a
  CLI or an API for the agent, with arguments as whole argv elements, a fixed host
  and secrets from the environment, scrubbed from output.
- Project trust: a project's own tools and verify command run only after
  `edgar trust`; `--no-project-exec` runs without them.
- `-p` for programs: `--json` (one object), `--events` (JSON Lines), `--quiet`,
  `--show-thinking`, `--no-color` and `NO_COLOR`; piped stdin is attached as
  context; a status line on stderr when it is a terminal; Ctrl-C exits 7.
- Sessions (M5): every session is recorded to `.edgar/sessions/<id>.jsonl`
  (git-ignored, one JSON object per line). `edgar --resume [ID]` and `--continue`
  reopen one, compacted view and all; `edgar sessions list|show ID|rm ID`; in the
  REPL `/sessions`, `/load ID`, `/new`, `/reset`, `/undo [N]` (files stay as they
  are, and it says which) and `/retry`.
- Long sessions compact themselves (M5): old tool results become one-line stubs,
  then old turns fold into one summary, cheapest first; `/compact [FOCUS]` does it
  now. Content that cannot fit the window stops with a hint instead of being cut.
- Cost caps: `[budget] turn_cost_cap` and `session_cost_cap` stop the turn before
  the next request; `-p` exits 6 with the partial result. With a cap set, a model
  of unknown price stops at once.
- `personality.md` (project `.edgar/` or `~/.edgar/`) for tone and style, shown by
  `edgar prompt show`; `~/.edgar/AGENTS.md` for instructions in every project.
- A warning at start when edgar's own control files (AGENTS.md, config, tools)
  changed during the previous session.

## 0.0.2 — 2026-09-13

### Added
- An `edgar-harness` command, so `uvx edgar-harness` works.

## 0.0.1 — 2026-09-13

### Added
- The package skeleton (M0): `edgar --version` on Linux, macOS and Windows,
  Python 3.12 and 3.13.
