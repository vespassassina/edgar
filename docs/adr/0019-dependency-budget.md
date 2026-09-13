# ADR-0019 — Five required dependencies: drop pydantic, tomli-w, platformdirs and keyring

**Status:** Accepted · 2026-09-13 · Amends BLUEPRINT §16, ADR-0012 and NFR-5

## Context

BLUEPRINT §16 allocated seven of eight dependency slots: `httpx`, `pydantic`,
`jsonschema`, `prompt_toolkit`, `rich`, `tomli-w`, `platformdirs`, one reserved.
Two needs were missing from the list:

- **A YAML parser.** `SKILL.md` and agent files use YAML frontmatter, and the
  standard library has no YAML parser
- **`keyring`**, which CFG-6 requires for OS keyring secrets

That is nine before MCP or a tokeniser. Separately, `pydantic` sat on the startup
path whatever the import test said: config is validated on every run, including a
trivial `-p`, so its import cost lands before the first byte (ADR-0012).

## Options

**A. Raise the cap to ten.** Honest about the list. Weakens the constraint that
keeps the project small.

**B. Remove what the design no longer needs**, write the rest from the standard
library, and make rarely used features optional extras.

**C. A frontmatter subset parser** instead of a YAML dependency. One fewer
dependency, and it rejects valid community skills that use YAML features the subset
lacks, which works against "open".

## Decision

Option B, with a real YAML parser.

**Required (5):**

| Package | Purpose | Loaded |
|---|---|---|
| `httpx` | HTTP and streaming for providers, `fetch`, HTTP tools, MCP over HTTP | lazily, first request |
| `jsonschema` | tool arguments, controller proposals, extension manifests | lazily, first validation |
| `PyYAML` | frontmatter in skills and agents, `safe_load` only | lazily, first discovery |
| `prompt_toolkit` | REPL input, history, steering | interactive path only |
| `rich` | markdown rendering, status line | interactive path only |

**Optional extras (counted toward the cap):**

| Extra | Purpose |
|---|---|
| `edgar-cli[keyring]` | read secrets from the OS keyring; env vars always work without it |

Two slots stay free.

**Removed:**

- **`pydantic`** — config is validated by hand-written code over `dataclasses` and
  `tomllib`. It produces better errors (file, key, expected type, a hint), which is
  what CFG-3 asks for, and costs nothing at import. Proposals and manifests are
  validated with `jsonschema`, which is needed anyway
- **`tomli-w`** — machines never rewrite TOML (ADR-0021). The two human-invoked
  commands that write TOML, `edgar init` and `edgar schedule add`, render from
  string templates and create or append, so comments and formatting survive
- **`platformdirs`** — config lives in `~/.edgar` on all three platforms (BLUEPRINT
  §15), and logs and caches derive from it
- **`keyring`** — becomes the optional extra above

**Import rule** (ADR-0012, CI-enforced): `import edgar.cli.main` pulls in none of
`httpx`, `rich`, `prompt_toolkit`, `jsonschema`, `yaml`, `keyring`, or any
`edgar.providers.*` module.

## Consequences

- **Every required dependency is off the trivial `-p` path.** The startup budget no
  longer depends on how fast `pydantic` imports
- **Config validation is code the reader can see**, about 200 lines in
  `config/schema.py`, and it teaches what a good validation error looks like
- **Skill discovery pays the YAML import** once per session when skills exist.
  Parsed frontmatter can be cached by path and mtime in the DB if that shows up in
  profiling
- **`docs/DEPENDENCIES.md`** (M11) lists each dependency with its measured import cost
- **Load-bearing:** optional extras must degrade loudly. Without `keyring`
  installed, a config that names a keyring secret fails with a hint naming the
  extra, never with a silent empty key

## Rejected alternatives

**A (raise the cap)** is rejected because the cap is what forces the questions
this ADR answers.

**C (subset parser)** is rejected on openness: users will copy skills from other
harnesses, and "your valid YAML is not our YAML" is a bad first experience.
Revisit if PyYAML's import cost ever becomes a startup problem.

**`msgspec` or `attrs` instead of hand-written validation** were considered.
Both are good, and both are a dependency to save code that is better read than
hidden.
