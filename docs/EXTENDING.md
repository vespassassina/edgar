# Extending edgar

Five surfaces, in the order most people reach for them. The first four need no
Python and no `edgar` source at all — a folder under `.edgar/` (or `~/.edgar/`
for every project) is enough. Only a provider is Python, and only because a
network protocol cannot be described in TOML. Quick recipes for four of these
are already in the [Cookbook](COOKBOOK.md); this page goes one layer deeper,
into the format each one is checked against.

## A tool

Two kinds need no code: a **command tool** (an argv template, started directly,
never through a shell) and an **HTTP tool** (a request template with a fixed
host). Both are one TOML file under `.edgar/tools/` or `~/.edgar/tools/`.

```toml
name = "gh_issue"                 # ^[A-Za-z0-9_-]{1,64}$
description = "Read a GitHub issue with the gh CLI."
argv = ["gh", "issue", "view", "{number}", "--json", "title,body,comments"]
read_only = true                  # true: allowed without asking, like `read`
[input]                           # a JSON Schema object; {name} slots must appear here
type = "object"
required = ["number"]
properties.number = { type = "integer" }
```

An HTTP tool replaces `argv` with `method`, `url`, `headers` and `body`; `{slot}`
fills the path, query and body, never the host, and `${env:NAME}` fills only
`url`'s base and header values from the environment — never sent verbatim to
the model, since every value it resolves is scrubbed from what the tool
returns. `edgar tools describe NAME` shows the schema exactly as the model
sees it; `edgar trust` is required once per project before either kind runs,
which is the whole reason `argv`/`url` are fixed at file-write time rather
than built at call time. See
[`tools/custom.py`](https://github.com/vespassassina/edgar/blob/main/src/edgar/tools/custom.py)
for the full grammar.

A third kind needs no TOML either: an **MCP server**, `[mcp.NAME]` in config,
covered in BLUEPRINT and `edgar mcp list|test`. Nothing here is a Python
built-in tool — that surface exists only inside `src/edgar/tools/builtin/`
and is not a plugin point (ADR-0018): a built-in tool is part of Core, added
by the maintainer, not an extension.

## A subagent

One flat markdown file under `.edgar/agents/` or `~/.edgar/agents/`, no
bundled resources:

```markdown
---
name: code-reviewer                              # ^[a-z0-9]+(-[a-z0-9]+)*$
description: Reviews a diff or a file for bugs.  # what the model reads to pick it
tools: [read, ls, glob, grep]                     # a subset of what the caller has
mode: read-only                                   # never wider than the caller's own
---

You review code. …the rest of the file is the agent's system prompt.
```

`task` appears as a tool once any agent file exists; there is no
`edgar agents list|validate` (cut from 1.0, ADR-0053), so the fastest check is
`edgar tools list` for its presence and a real call to see it run. `mode` can
only narrow the calling session's mode, never widen it [PERM-8] — an agent
asking for `auto` inside a `read-only` session is refused, not upgraded. A
project agent silently replaces a same-named user one, with a warning.

## A skill

A folder under `.edgar/skills/` or `~/.edgar/skills/`, named for its skill,
holding a `SKILL.md` and anything the skill's body refers to by relative path
(a template, a script):

```markdown
---
name: changelog                     # must equal the folder name
description: Use when adding an entry to CHANGELOG.md.
---

# Writing a changelog entry
1. …
```

Only `name` and `description` are loaded into every prompt; the body loads
either when the model calls the `skill` tool, or automatically the moment a
keyword the user typed or a path the last round touched matches — write the
description as *when to use it*, since that sentence is all the model sees
before deciding. A script beside `SKILL.md` runs through the `shell` tool
under the same permission checks as any other command; nothing about a skill
needs `edgar trust`, since a skill is instructions, never code that runs on
its own. `edgar skills validate` lints the folder.

## An extension

A folder under `.edgar/extensions/NAME/` (or `~/.edgar/extensions/NAME/`)
bundling any of the above, plus hooks and MCP servers, behind one manifest:

```toml
# .edgar/extensions/my-extension/extension.toml
name = "my-extension"               # must equal the folder name
version = "0.1.0"
description = "What this bundle adds."
[requires]
edgar = ">=1.0"                     # optional; both requires.* checks are advisory
commands = ["gh"]
```

```
.edgar/extensions/my-extension/
  extension.toml
  tools/       # same TOML tools as above, tagged ext:my-extension
  skills/      # same SKILL.md folders
  agents/      # same flat markdown files
  hooks.toml   # [[hooks]] — see below
```

Everything an extension bundles folds straight into the project's own tools,
skills and agents [EXT-8]; a collision is won the same way a plain project
file would win, project over user. `edgar ext list` shows what loaded and
what it brought; there is no `ext validate`/`ext add` in 1.0 (ADR-0053), so
installing one is `cp -r` or a submodule, and validating it is running
`edgar tools list`/`edgar skills list`/`edgar ext list` and reading the
warnings.

A `hooks.toml` (or `[[hooks]]` directly in config, for a project's own,
unbundled hooks) declares shell commands the harness runs at lifecycle
points:

```toml
[[hooks]]
event = "pre_tool"                  # only pre_tool can deny anything
command = ["./check.sh"]
match = { tool = "shell" }          # optional: only when this key/value matches
timeout_s = 30
```

The event as JSON arrives on the command's stdin. `pre_tool` is the only
event that can stop anything: exit 2 denies the call with stderr as the
reason shown to the model, and a hook that errors, times out, or exits any
other non-zero code also denies — it fails closed, never open. Every other
event (`session_start`, `post_tool`, `turn_end`, `verify_finished`,
`session_end`) is observation only: fired and forgotten, its exit code and
output never read, and nothing it prints reaches the model or memory
[EXT-6, EXT-7]. See
[`extensions/hooks.py`](https://github.com/vespassassina/edgar/blob/main/src/edgar/extensions/hooks.py).

## A provider

The one surface that is Python, because there is no way to describe an HTTP
API's streaming and tool-call shape declaratively without ending up with a
second programming language. Two ways in, neither touching `src/edgar/`:

**A user-defined OpenAI-compatible server** needs no code at all — a
`[providers.NAME]` block:

```toml
[providers.my-server]
kind = "openai-compatible"
base_url = "https://my-server.example/v1"
api_key_env = "MY_SERVER_API_KEY"
```

This is enough for anything that speaks the OpenAI chat-completions shape;
`providers/quirks.py`'s `Quirks` dataclass is the full list of what else can
be adjusted (`native_tools`, `max_context`, `parallel_tools`, and so on) —
read it before assuming a mismatch needs new code, since almost every
real-world difference between OpenAI-compatible servers is a data row there,
never a branch in `openai_compat.py` (ADR-0002, ADR-0020).

**A genuinely different wire protocol** is an installed package registering
an `edgar.providers` entry point named for it:

```toml
# the plugin's own pyproject.toml
[project.entry-points."edgar.providers"]
my-provider = "my_package.adapter"
```

`my_package.adapter` needs a module-level `make(name, quirks, *, api_key,
prices, transport=None, **options) -> Provider` returning something that
satisfies the `Provider` protocol in
[`providers/base.py`](https://github.com/vespassassina/edgar/blob/main/src/edgar/providers/base.py):
`stream()` (an async call that returns one `ProviderResponse` — `edgar`'s own
canonical `Message`, never a provider-native structure), `count_tokens()`,
`models()`, and a `capabilities` attribute. `registry.py`'s `resolve()` tries
a built-in, then a `[providers.NAME]` block, then this entry point, in that
order, and imports nothing until a model string actually names it [PRV-4,
PRV-9].

There is no shipped, importable contract-test kit for a third-party provider
in 1.0 (`edgar.testing.contract` was cut, ADR-0053) — the parametrised suite
every built-in adapter passes,
[`tests/contract/test_provider_contract.py`](https://github.com/vespassassina/edgar/blob/main/tests/contract/test_provider_contract.py),
is what "a new provider is done" means for code contributed to edgar itself,
and is the reference to read even without importing it. A third-party plugin
should still hand-test streaming, cancellation and tool-call translation
against it; that gap moves to v2.
