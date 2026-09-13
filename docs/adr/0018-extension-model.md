# ADR-0018 — Tools, skills and extensions: one vocabulary, files first, Python last

**Status:** Accepted · 2026-09-13 · Amends ADR-0003

## Context

The goal is a harness that is extensible and open, and whose agents can use the
command-line tools and web APIs people already have. ADR-0003 set up four sources
(built-in tools, custom shell-out tools, MCP, skills). Three things were missing.

**No way to call an API without writing an MCP server.** Custom tools shelled out
to a command. Calling a REST endpoint meant `curl` through the shell tool, with the
API key in the command line and the URL chosen by the model.

**No way to package.** A useful integration is usually a few tools, a skill that
explains them and maybe an agent. There was no unit to share, so sharing meant
copying five files into the right five folders.

**No way to react to what the agent does** without editing Python: run a formatter
after an edit, block a command pattern with a real script, notify on completion.

Two constraints shape the answer. The non-goals rule out a registry or marketplace
(PRD §5.2). And every extension surface has to stay a file a person can read and
diff (PRD principle 8).

## Options

**A. Python plugin API for everything.** Entry points for tools, hooks and
providers. Most powerful. Makes the Python API a compatibility promise, excludes
non-Python users, and scanning entry points costs startup time.

**B. MCP for everything.** Any code-bearing tool is an MCP server. Language-neutral
and already specified. Too heavy for "call this one endpoint" or "run `gh issue
view`", and it does not cover packaging or hooks.

**C. Declarative files for common cases, MCP for code, Python only for providers.**

## Decision

Option C. The vocabulary, one line each:

| Term | What it is | Written as | Tier |
|---|---|---|---|
| **Tool** | A function the model calls | see the four kinds below | Core |
| **Skill** | Instructions and resources the model loads on demand | `SKILL.md`, Claude-compatible | Core |
| **Agent** | A subagent: model, tools, mode, budget, prompt | markdown + YAML frontmatter | v1 |
| **Hook** | A command run on a lifecycle event; can observe or veto, never allow | `[[hooks]]` in TOML | v1 |
| **Extension** | A folder bundling any of the above plus MCP servers | `extension.toml` + folders | v1 |
| **Provider plugin** | A Python package adding a model provider | entry point `edgar.providers` | v1 |

### Four kinds of tool

**Built-in** — Python, shipped: `read` `write` `edit` `ls` `glob` `grep` `shell`
`fetch` `skill` in Core; `task` `remember` `recall` in v1; `schedule_self` in v2.

**Command** — runs a CLI with an argv template. This is how agents get **CLI access**
beyond the raw `shell` tool:

```toml
# .edgar/tools/gh_issue.toml
name = "gh_issue"
description = "Read a GitHub issue, its body and comments, with the gh CLI."
argv = ["gh", "issue", "view", "{number}", "--json", "title,body,comments"]
timeout_s = 30
read_only = true            # human assertion: usable in read-only mode

[input]
type = "object"
required = ["number"]
properties.number = { type = "integer", description = "Issue number" }
```

Arguments are validated against the schema, then substituted as **whole argv
elements**, never interpolated into a shell string. There is no injection surface to
defend.

**HTTP** — calls a web API with a request template. This is **API access** without
code:

```toml
# .edgar/tools/forecast.toml
name = "forecast"
description = "Weather forecast for a coordinate."
method = "GET"
url = "https://api.example.com/v1/forecast?lat={lat}&lon={lon}"
headers = { Authorization = "Bearer ${env:EXAMPLE_API_KEY}" }
timeout_s = 20
read_only = true

[input]
type = "object"
required = ["lat", "lon"]
properties.lat = { type = "number" }
properties.lon = { type = "number" }
```

Three rules make this safe. The **host is fixed by the template**; model arguments
only fill path, query or body slots, URL-encoded or JSON-encoded by type, so the
model cannot redirect the request. **`${env:NAME}` resolves only in the base URL
and headers**, never from model arguments, and resolved values are redacted from
transcripts, events and logs. The **response is untrusted network content**, so it
sets the session taint (ADR-0021) and goes through spill (ADR-0016).

**MCP** — servers over **stdio** and **Streamable HTTP**, spawned lazily on first use,
namespaced `mcp__server__tool` [TOOL-7, TOOL-8]. The older HTTP+SSE transport,
replaced in the MCP specification's 2025-03-26 revision, is not supported. Remote
servers take static headers from the environment in v1; OAuth arrives in v2.
Server-declared annotations such as `readOnlyHint` are hints from the server and
never feed permission decisions. MCP output is untrusted and sets taint.

**Rule of thumb for users:** one command → command tool; one endpoint → HTTP tool;
real code or state → MCP server, in any language.

### Hooks

```toml
[[hooks]]
event = "pre_tool"                  # session_start · pre_tool · post_tool
match = { tool = "shell" }          # turn_end · verify_finished · session_end
command = ["./scripts/check-cmd.sh"]
timeout_s = 5
```

A hook receives the event as JSON on stdin. For `pre_tool`, exit 2 **denies** the
call and the hook's stderr becomes the reason the model sees; any other failure
also denies (fail closed), because a veto hook that silently stops working widens
the effective policy. Hooks cannot modify arguments and cannot allow anything
policy denies. Hook output never enters the model's context or memory, apart from
a deny reason. The schedule `on_complete` hook becomes a `session_end` hook.

### Extensions

```
.edgar/extensions/github/
├── extension.toml
├── tools/        gh_issue.toml, gh_pr.toml
├── skills/       triage/SKILL.md
├── agents/       reviewer.md
├── hooks.toml
└── mcp.toml
```

```toml
# extension.toml
name = "github"
version = "0.2.0"
description = "Issues and pull requests through the gh CLI"
requires = { edgar = ">=1.0", commands = ["gh"] }
```

Discovered at `./.edgar/extensions/` and `~/.edgar/extensions/`. Enabled by being
there; disabled with `extensions.disabled = ["github"]`. `edgar ext list` and
`validate` check the manifest and that required commands exist. `edgar ext add
PATH|GIT_URL` copies a folder in and records the source and commit in the
manifest. There is no index, search or update service, so this is copying, not a
marketplace, and stays inside PRD §5.2.

Collision order is `project custom > user custom > extensions (by name) > MCP >
built-in`, with a startup warning [TOOL-9].

### Python, only for providers

A package can register a provider with an entry point:

```toml
[project.entry-points."edgar.providers"]
gemini = "edgar_gemini:make"
```

The registry reads entry points only when a model string names a provider it does
not know, so the startup path never pays for the scan. The provider contract suite
ships as `edgar.testing.contract`, so a plugin author runs the same tests the
built-in adapters pass. Tools in Python are deliberately not a plugin surface: MCP
already covers code-bearing tools in every language.

### Embedding edgar in other programs

No daemon and no HTTP API (PRD §5.2). Three surfaces instead, all thin layers over
the existing loop and event bus:

- `edgar -p … --json` — one result object (exists)
- `edgar -p … --events` — the event stream as JSON Lines on stdout, one event per
  line, for editors, CI and dashboards [CLI-18]
- `edgar.run(prompt, *, config=…, mode=…) -> TurnResult` — a documented async
  Python function [EXT-9]

## Consequences

- **The tinkerer never opens `src/`**, now including API calls and packaging
- **Command and HTTP tools are the highest value per line in the project**: roughly
  200 lines for both, on top of the tool pipeline that already exists
- **`read_only = true` is a human assertion**, recorded in a hand-authored file.
  It is trusted the way a permission rule is trusted
- **Executable project config needs trust.** A cloned repository can ship hooks,
  MCP servers and command tools that run on launch. ADR-0021 covers this
- **v1 freezes these formats** (ADR-0015), so they get the design care now
- **Load-bearing:** HTTP tools never let model arguments choose the host or read
  the environment. Loosening either turns every HTTP tool into a general exfiltration
  primitive

## Rejected alternatives

**A (Python for everything)** is rejected: it makes the least-open surface the
main one, and a tool API in Python duplicates what MCP does in every language.
Revisit tools-in-Python only if MCP's per-call overhead proves a real problem.

**B (MCP for everything)** is rejected for the common cases. A 15-line TOML file
is easier to read, review and share than a server process.

**OpenAPI import** (generate HTTP tools from a spec) is deferred to post-v2. It is
a good fit for the HTTP tool format and a generator, not a new mechanism.
