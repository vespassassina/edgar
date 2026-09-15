# Dependencies

Every runtime dependency edgar ships, why it exists, and what it actually
costs to import — the cap NFR-5 sets is 8 direct dependencies, counting
optional extras, and this page is how that number stays checked rather than
assumed. Measured with `python -X importtime -c "import X"`, the cumulative
column, on the versions locked in `uv.lock` at the time this page was last
updated (see git history for the date); re-measure before trusting a number
to the millisecond, since a version bump can move it either way.

| Package | Version | Purpose | Loaded | Measured import cost |
|---|---|---|---|---|
| [`httpx`](https://www.python-httpx.org/) | 0.28.1 | HTTP and streaming for every provider adapter, the `fetch` and HTTP tools, and MCP over Streamable HTTP | lazily, on the first network call a session actually makes | ~45 ms |
| [`jsonschema`](https://python-jsonschema.readthedocs.io/) | 4.26.0 | validates tool arguments against their schema, and extension manifests | lazily, on the first tool call or extension discovery | ~38 ms |
| [`PyYAML`](https://pyyaml.org/) (`import yaml`) | 6.0.3 | `safe_load` only, for a skill's or agent's frontmatter | lazily, the first time a project has a skill or agent to discover | ~9 ms |
| [`prompt_toolkit`](https://python-prompt-toolkit.readthedocs.io/) | 3.0.53 | the REPL's input line, history file, and steering a running turn | only on the interactive path; never for `-p` | ~60 ms |

**Optional extra, counted toward the cap:**

| Extra | Version | Purpose | Loaded | Measured import cost |
|---|---|---|---|---|
| `edgar-harness[keyring]` (`import keyring`) | 25.7.0 | reads a provider's key from the OS keyring instead of the environment [CFG-6] | only if installed and a session actually reads a keyring-stored secret | ~49 ms |

Four required, one optional: five of the eight slots NFR-5 allows, three
free. `import edgar.cli.main` — the module every invocation loads first —
pulls in none of the above, nor any `edgar.providers.*` adapter; a CI test
(`tests/e2e/test_startup.py`) enforces this on every push, the same way it
enforces the ≤ 150 ms startup budget [NFR-1, ADR-0012]. A trivial `-p` run
against the fake provider therefore never imports `httpx`, `jsonschema`,
`yaml`, `prompt_toolkit` or `keyring` at all — only a session that actually
calls a tool, discovers a skill or agent, opens the REPL, or reads a keyring
secret pays that package's cost, and only once, on first use.

## Why not more, and why not fewer

[ADR-0019](adr/0019-dependency-budget.md) explains the four removed before
1.0 — `pydantic` (config validation is hand-written over `dataclasses` and
`tomllib`, for better error messages at zero import cost), `tomli-w`
(nothing rewrites TOML; `edgar init` renders from a string template),
`platformdirs` (config always lives under `~/.edgar`), and `keyring` itself
(demoted from required to the optional extra above). That ADR's decision
table also names `rich` as a fifth required dependency, planned for markdown
rendering and the status line; it never shipped, because `cli/render.py`'s
own small renderer turned out to cover both without it. This page describes
what actually ships, which is four required and one optional — a stale
mismatch worth fixing in the ADR itself, not a second source of truth to
maintain here.

## Adding one

A sixth dependency needs the same case ADR-0019 made for the current four:
what it replaces, its measured import cost added to this table, and where it
sits on the lazy-import boundary (interactive-only, tool-call-only, or
genuinely on the startup path, which should be rare enough to justify an ADR
of its own). `docs/adr/` is where that argument gets written down before the
`pyproject.toml` line lands.
