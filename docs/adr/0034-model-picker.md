# ADR-0034 — A model picker that asks, lists on request, and never edits your config

**Status:** Accepted · 2026-09-13 · Adds CLI-30; lands in M4

## Context

The maintainer asked for a way to choose and configure a model from inside edgar,
instead of writing TOML by hand. Two rules constrain it:

- `config.toml` is hand-authored, and no automated process modifies it
  (ADR-0007, ADR-0008). BLUEPRINT §16 dropped `tomli-w` because machines never
  rewrite TOML.
- edgar contacts no host the user did not choose (PRV-15). Listing a provider's
  models is a request to that provider.

## Decision

**`edgar models`** (with no subcommand) is an interactive picker, and `/model`
with no argument opens the same picker in the REPL [CLI-30].

1. **Provider.** It lists every built-in and configured provider, with its
  endpoint and whether its key is set (as `edgar models list` does).
2. **Model.** It fetches that provider's model list from the provider's own
  endpoint (`GET /v1/models`, or Ollama's list), only after the user picks the
  provider. The host is printed first. The user may also type a model name, and
  nothing is fetched then.
3. **Where it goes.** `/model` switches for the current session only
   (CLI-28). `edgar models` asks whether to make it the default:
   - if the chosen file (`~/.edgar/config.toml` or `.edgar/config.toml`) does not
     exist, it is **created** with the `[model]` block, and a `[providers.NAME]`
     block when one is needed. Creating a file is what `edgar init` does too
     (CFG-4);
   - if the file exists, edgar **prints the lines to add and where**, and does
     not touch it.
4. **Keys.** The picker never asks for or stores a key. For a missing key it
   prints the variable to export, or `edgar login` where the provider supports it
   (ADR-0032).

## Consequences

- A user can go from nothing to a working setup without opening an editor, and an
  existing hand-written config is never rewritten behind their back.
- Listing remote models is the only network call the picker makes, and it happens
  only after the user picks a provider.
- The picker needs `prompt_toolkit` (the interactive path's dependency), so it
  lands with the REPL in M4.
