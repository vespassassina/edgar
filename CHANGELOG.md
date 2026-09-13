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
- `-p` for programs: `--json` (one object), `--events` (JSON Lines), `--quiet`,
  `--show-thinking`, `--no-color` and `NO_COLOR`; piped stdin is attached as
  context; a status line on stderr when it is a terminal; Ctrl-C exits 7.

## 0.0.2 — 2026-09-13

### Added
- An `edgar-harness` command, so `uvx edgar-harness` works.

## 0.0.1 — 2026-09-13

### Added
- The package skeleton (M0): `edgar --version` on Linux, macOS and Windows,
  Python 3.12 and 3.13.
