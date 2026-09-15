# Changelog

What changed for people using edgar, newest first. The reasons live in
[`docs/adr/`](docs/adr/), the day-by-day record in [`docs/JOURNAL.md`](docs/JOURNAL.md).
Versions follow the tiers in [`docs/ROADMAP.md`](docs/ROADMAP.md): 0.0.x while
Core was being built, 0.1 the first release you can work in, 1.0 when v1's
extension formats freeze.

## Unreleased

### Added
- Subagents. A `task` tool appears once any agent is discovered in
  `.edgar/agents/` or `~/.edgar/agents/`: pick one by name and it runs in a fresh
  session, with its own model (routed for role `subagent`, or its own
  frontmatter `model:`), its own tool subset, and a `mode:` that can only ever
  narrow the calling session's, never widen it. It shares the parent's
  permission guard, so its prompts ask one at a time alongside the main turn's
  own and are labelled with the agent's name; its budget is capped at whatever
  the parent has left to give, and a result that ran out of budget says so
  rather than passing a truncated answer off as whole. An agent already running
  above itself, or a call past `[subagents] max_depth`, is refused rather than
  run. Ask the model for several subagents in the same turn and they run
  together, bounded by `[subagents] max_parallel`; everything else still runs
  one call at a time, and results come back in the order they were asked for,
  not the order they finish.
- Each subagent running now gets its own row under the main status line, so
  two or more running together never interleave into one confusing stream; a
  row appears when its `task` call starts and disappears once it finishes.
- An example agent, `examples/agents/code-reviewer.md`: copy it into
  `.edgar/agents/` and the `task` tool can hand it a diff or a file to review
  read-only, with no `write`, `edit` or shell access.
- A model with no tool support is now refused where it is chosen — a subagent
  asking for one gets a plain tool error back; the main session choosing one
  with `/model` or at startup gets a config error — instead of failing
  confusingly the first time a turn tries to call a tool.
- Extensions: a folder under `.edgar/extensions/` bundling tools, skills,
  agents and one `hooks.toml`, found the same way skills and agents already
  are. `edgar ext list` shows what is discovered. A hook can observe or veto,
  never allow — every kind fires as an event, and `pre_tool` alone runs just
  before the permission check; a hook that errors, times out or exits
  non-zero denies the call rather than letting it through.
- Provider plugins: a third-party package can register a provider through the
  `edgar.providers` entry point; nothing is imported unless a session actually
  names it.
- Skills can now activate on their own: a keyword the user typed or a path the
  last round touched loads a matching skill straight into the turn, with no
  need for the model to call the `skill` tool first. A skill's own `verify:`
  command now also takes its place in the verify precedence chain, below
  `--verify` and an agent's own frontmatter.
- `edgar.run()`: an async Python function to embed edgar in another program —
  build a session and run one turn the same way the CLI does, with your own
  event subscribers and your own function to answer permission prompts.
  `import edgar` stays as light as `import edgar.cli.main`.
- Three more slash commands: `/agents` lists the subagents this session's
  `task` tool can run, `/skills` lists the skills it can load, `/tools` lists
  every tool available.

### Changed
- A `[[route]]` rule with a key edgar does not recognise is now a config error
  naming the rule. A misspelt condition used to be dropped, so the rule matched
  every turn.
- `/plan` says it arrives in v2; plan mode moved there before 1.0.
- `edgar models` offers to sign in instead of sending you away. Picking a provider
  that has no key but can issue one through the browser now asks "no key for
  openrouter. Sign in now? [Y/n]" — Enter signs in and the picker carries straight
  on to that provider's models, using the key it just got even if there is no
  keyring to keep it in. Answer `n` and you get the old message naming the
  environment variable. A provider with no browser sign-in (OpenAI, Anthropic) is
  unchanged: its key is named, never asked for.

### Fixed
- Two sessions started within the same millisecond (a fork right after its parent,
  a script starting several) could sort in the wrong order, so `edgar --continue`
  could reopen the older one. An id now never reuses the previous one's
  millisecond.
- The tour said M7 to M17 were planned; M7 (memory) and M8 (MCP, signing in) have
  been built since 0.1.0. It now says M0 to M8 built, M9 to M17 planned.

### Security
- `fetch` and any HTTP tool could be sent to the cloud instance-metadata address
  (169.254.169.254 and the rest of that range) in `auto` mode before the session
  was even tainted, and in `yolo` always. A URL that literally names a link-local
  address is now denied in every mode, the same hard layer as catastrophic shell
  commands. A hostname that merely resolves there still gets through; see
  [ADR-0049](docs/adr/0049-network-hard-layer.md) for what this does and does not
  cover.

## 0.1.0 — 2026-09-14

The first release that is a harness rather than a skeleton: Core (M0–M6) whole,
plus memory, session forks, MCP and signing in from v1 (M7, M8). 6,809 lines of
code of the 8,000 v1 is allowed.

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
