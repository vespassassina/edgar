# ADR-0027 — Distribute as `edgar-harness` on PyPI; the command stays `edgar`

**Status:** Accepted · 2026-09-13 · Amends the package name in ADR-0001, ADR-0019 and ADR-0022

## Context

The spec named the PyPI distribution `edgar-cli`. PyPI refused to register it:
names are compared after lower-casing and removing `-`, `_` and `.`, and
`edgar-cli` collides with the existing project `edgarcli`. The name has to change
before the first release, and after that it is effectively permanent.

The `edgar-*` namespace on PyPI is crowded with about thirty packages about SEC
EDGAR filings (`edgartools`, `edgar-sec`, `edgar-parser`, `edgar-agent-tool` and
others), so a new name should say what this project is.

## Options

**A. `edgar-harness`.** Matches the headline, "the agent harness you can read in
an afternoon", and cannot be mistaken for an SEC tool.

**B. `edgar-agent`.** Shorter, but close to `edgar-agent-tool`, which is an SEC
filings tool.

**C. `edgar-sh` or `edgar-code`.** Short. The first says little; the second
narrows edgar to coding when it also drives CLIs and APIs.

## Decision

**`edgar-harness`.** Only the distribution name changes:

| | Name |
|---|---|
| PyPI distribution | `edgar-harness` |
| Install | `uvx edgar-harness`, `uv tool install edgar-harness` |
| Optional extra | `edgar-harness[keyring]` |
| Command | `edgar` |
| Import package | `edgar` |

ADR-0001, ADR-0019 and ADR-0022 say `edgar-cli`; read that as `edgar-harness`.
`BRAINSTORM.md` keeps the old name as a historical record.

## Consequences

- `uvx edgar-harness` is longer to type than `uvx edgar-cli`. After
  `uv tool install edgar-harness`, the command is `edgar`.
- **The import name `edgar` is shared.** `edgartools`, a popular SEC-filings
  library, also installs a top-level package called `edgar`. Installed side by side
  in one environment, one overwrites the other. This does not affect the CLI, since
  `uvx` and `uv tool` give edgar an isolated environment. It does affect embedding
  (`edgar.run()`, EXT-9) and plugin authors, who share an environment with the host
  program. Revisit before the embedding API freezes in v1 (M10): renaming the import
  package then is cheap; after 1.0 it is a breaking change.

## Rejected alternatives

**`edgar-agent`** and **`edgar-code`**, for the reasons above. What would change
the answer: the import-name clash with `edgartools` proving to be a real problem,
in which case the distribution and import names should change together, for
example to `edgar_harness`.
