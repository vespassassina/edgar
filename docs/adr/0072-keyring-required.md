# ADR-0072 — `keyring` is a required dependency

**Status:** Accepted · 2026-10-02 · Amends ADR-0019 (the dependency budget)

## Context

`keyring` was an optional extra (ADR-0019, ADR-0032). `edgar login` signed you
in, found no keyring, printed the key once and kept nothing, and told you to
reinstall with an extra. The maintainer hit that on the first Copilot sign-in
and called it "ultra annoying". Signing in that forgets you is a worse default
than one more small dependency.

## Decision

`keyring>=25` moves into `dependencies`. It is still imported lazily, so
`import edgar.cli.main` loads nothing new and the startup budget (NFR-1) is
untouched. The `[keyring]` extra stays as an empty alias so an old install line
does not warn. Five of the eight dependency slots (NFR-5) are used.

## Consequences

- macOS and Windows have a backend built in. A bare Linux box may have none; the
  message then says to export the key as an environment variable instead of
  telling you to install something that is already installed.
- Rejected: auto-installing at login time. A tool that runs `pip` on its own is
  hidden behaviour (PRV-15), and it breaks under `uvx` and `uv tool`.
