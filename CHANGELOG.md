# Changelog

What changed for people using edgar, newest first. The reasons live in
[`docs/adr/`](docs/adr/), the day-by-day record in [`docs/JOURNAL.md`](docs/JOURNAL.md).
Versions follow the tiers in [`docs/ROADMAP.md`](docs/ROADMAP.md): 0.0.x while
Core is being built, 0.1 at the Core release (M6).

## Unreleased

### Added
- [A Tour of the Harness](https://vespassassina.github.io/edgar/): a guided read
  of the code, stop by stop, with diagrams, one part per tier, styled with
  artifactkit on a dark midnight theme.
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
- Skills (M6): a folder with a `SKILL.md`, in the format Claude uses, in
  `.edgar/skills/` or `~/.edgar/skills/`. The prompt lists each skill's name and
  description; the model loads the rest with the `skill` tool when it fits. A
  project's skill replaces a user one of the same name, with a warning at start.
  A broken `SKILL.md` is skipped with its reason, never fatal.
- `edgar skills list|validate` (validate exits 1 when a skill has a problem) and
  `edgar tools list|describe NAME`, which shows the tools a session here gets.
- `examples/`: a command tool, an HTTP tool and a skill to copy, and
  [`docs/COOKBOOK.md`](docs/COOKBOOK.md), short recipes for the first week.
- A quick start in the README.
- Sign in without a key: `api_key_command` in a `[providers.NAME]` block of
  `~/.edgar/config.toml` runs your cloud's CLI (`az account get-access-token`,
  `gcloud auth print-access-token`, or AWS's Bedrock token generator) and sends
  its token, refreshed every ten minutes. Works for Azure with keys switched off,
  Google Vertex AI and Amazon Bedrock; recipes in the Cookbook.
- Memory (v1, M7): `/remember TEXT` or `edgar memory add TEXT` saves a fact, and
  from the next session it is in the prompt as a note, not an instruction.
  `edgar memory list|edit|review|forget ID|undo` shows and changes what edgar
  remembers; `edit` opens the facts as markdown in your editor, and `undo` takes
  back the last change whole. When the model proposes a fact with `remember`,
  edgar asks `save? [y/N]` at the end of the turn; Enter forgets it. Secrets are
  redacted before anything is stored.
- `recall`: the model searches remembered facts and past sessions' conversation
  (never tool output), by word and by fragment of a path or identifier. `[memory]`
  in config sets how many facts are pinned (20) and the cap per scope (500).
- Session forks (M7): `/fork` or `edgar --fork ID[@TURN]` branches a session into
  a new one, from its latest turn or from turn N; the original is untouched.
- `/save [PATH]` writes the session to one file with spilled tool output included
  and secrets redacted; `/load PATH` or `edgar --load PATH` opens it as a new
  session. `/history` shows the whole conversation, compacted turns included.
- `[budget] daily_cost_cap`: the day's spend across every project; a turn gets
  what is left of it as its cap, and once it is spent turns stop with exit 6.
  `edgar cost` shows today and the last seven days; `/cost` adds today's total.
- MCP servers (v1, M8): `[mcp.NAME]` blocks in config, over stdio (`command`) or
  Streamable HTTP (`url`). Nothing starts when a session starts: edgar remembers
  what each server offered last time and starts the server on the first call, so
  five configured servers cost a session nothing. Their tools are named
  `mcp__server__tool`, their results are untrusted (they tighten what the rest of
  the session may do), and what a server claims about its own tools is shown to
  you, never used to decide. `${env:NAME}` in `env`, `url` and `headers` is read
  when the server starts and redacted from everything it sends back.
- `tool_search`: when the tool schemas would cost more than `[tools]
  schema_budget` (4,000 tokens), the MCP ones are listed by name and one line and
  their full schemas are loaded on demand, for the rest of the session.
- `edgar mcp list` shows every configured server and its tools, with the hints the
  server publishes; `edgar mcp test NAME` starts one server and reports what it
  answered. A project's `[mcp.NAME]` needs `edgar trust` first.
- `/browser`: with `[browser] tool = "..."` it checks the tool you already have,
  with `[browser] command = ...` it starts that MCP server for this session, and
  with neither it prints the block you could write. It never picks a browser.
- Signing in (M8): `edgar login openrouter` opens your browser, and the key the
  provider issues is yours, kept in your OS keyring with the optional extra
  (`pip install 'edgar-harness[keyring]'`) or printed once and stored nowhere.
  `edgar logout PROVIDER` forgets it here; revoke it where it was issued.
  `edgar models list` says which providers are signed in.
- `edgar mcp login NAME` signs in to a remote MCP server: OAuth 2.1 with PKCE, a
  redirect caught on a loopback port, the client registered on the spot, and a
  token scoped to that server. A turn never opens a browser by itself; a call to a
  server with no token fails with the command to run. `edgar mcp logout NAME`
  forgets it. Tokens are redacted from everything edgar prints or records.

### Changed
- `edgar sessions rm` refuses a session that has forks, since they read its file.
- `edgar models`: pressing Enter at "make it the default?" now saves it to your
  user config; it used to mean no.

## 0.0.2 — 2026-09-13

### Added
- An `edgar-harness` command, so `uvx edgar-harness` works.

## 0.0.1 — 2026-09-13

### Added
- The package skeleton (M0): `edgar --version` on Linux, macOS and Windows,
  Python 3.12 and 3.13.
