# ADR-0076 — `edgar keys`: one place for model and search keys

**Status:** Accepted · 2026-10-03 · Amends ADR-0032

## Context

A model key was an exported variable, or `edgar login` for the few providers that
issue one. A web search key had no command at all: the tool file reads
`${env:NAME}`, so the person had to export it in their shell profile. Both break
for apps started from the desktop, and neither belongs in a file (CFG-6).

## Decision

- `edgar keys` lists every model and search provider, its variable, and where the
  key is now: environment, keyring, or nowhere. `edgar keys set NAME` asks without
  echo (a pipe gives its first line) and keeps it in the OS keyring as
  `env:VARIABLE`; `remove NAME` forgets it. NAME is a provider, `search:NAME`, or a
  raw VARIABLE. A key is never printed.
- One lookup, `auth/store.secret(var, env)`: the environment first, the keyring
  second, and the keyring only when `env` is the real `os.environ`, so a test or a
  caller passing its own mapping never reaches it. Provider connect and
  `${env:NAME}` expansion both use it. Exporting a variable still wins.
- Tool files do not change, and project trust still guards them: a project's tool
  can name a variable, so `edgar trust` is what stops it taking another one.

## Alternatives

- Write a gitignored `.env`: a second place to leak from, and edgar reads no files
  for keys today.
- A keyring account per provider name: search tools have no provider name.

## Consequences

The keyring is read only when a variable is unset. No keyring: `set` says so and
the variable route still works. About 80 lines of code, over the margin by that
much (ceiling 10,450).
