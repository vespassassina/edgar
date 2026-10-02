# ADR-0073 — The first model pick is saved for every project

**Status:** Accepted · 2026-10-02 · Amends ADR-0034

## Context

Starting edgar with no model set opens the picker (ADR-0034). The choice was
written only into that directory's own `.edgar/config.toml`, so every new
directory asked for the provider again, and scaffolded `AGENTS.md` and the
wizard questions each time. The user's `~/.edgar/config.toml` (from an earlier
`init`) had `default` commented out, and `remember()` never edits an existing
file.

## Decision

- After a pick at startup, `init.run` saves the default to the user config
  (`~/.edgar/config.toml`), through `remember()`.
- `remember()` fills in one thing in an existing file: the unedited placeholder
  line `# default = "provider/model"` that `edgar init` itself wrote. It is
  edgar's own blank, not something a person wrote. Any other existing file is
  still left alone, and the line to add is printed.

## Consequences

- One pick, every project. The next start in any directory goes straight to the
  REPL.
- A user config a person edited has no placeholder; they get the two lines to
  paste, and are asked again until they do. `edgar models` offers the same save.
