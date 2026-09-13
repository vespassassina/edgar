# ADR-0012 — 150 ms startup as an enforced constraint

**Status:** Accepted · 2026-09-02

## Context

ADR-0001 chose Python knowing its weakness is process startup. For a tool meant to
be used in pipes, possibly in a loop over many files, startup latency is the
difference between a tool people compose with and one they avoid.

CPython itself starts in roughly 30 ms. Imports account for everything after that.
Eagerly importing three provider SDKs, pydantic and rich puts first output past
400 ms before a single token moves.

Left as a guideline, this constraint erodes. Every feature adds one more
"harmless" top-level import and nobody notices until the tool feels sluggish and
the cause is spread across forty files.

## Decision

**150 ms from process start to first byte of output**, measured on a trivial `-p`
invocation against the fake provider, on 2020-era laptop hardware.

Enforced as a CI test **from milestone 1**, before there is any feature to regress.

Two tests, not one:

1. **Wall-clock**: subprocess timing of a trivial run, with generous CI tolerance
2. **Import graph assertion**: `import edgar.cli.main` must not pull in any
   provider module, `httpx`, `rich`, or `prompt_toolkit`

The second test is the one that actually holds the line. Wall-clock timing on
shared CI runners is noisy; an import assertion is exact and its failure message
names the offending module.

## Consequences

This constraint **shapes the architecture rather than merely checking it**:

- **Providers load lazily** behind a registry of thunks (ADR-0002). No provider
  module is imported until a model string is resolved
- **`rich` and `prompt_toolkit` are interactive-path only.** The `-p --json` path
  never imports them, which the event bus (ADR-0011) makes natural
- **MCP servers spawn on first use, not at startup** (ADR-0003). Five configured
  servers would otherwise mean five process launches per invocation
- **`pydantic` is on probation.** It is in the dependency budget for config and
  proposal validation, and if its import cost breaks the budget it gets replaced
  with `dataclasses` plus `jsonschema`. This is written down so the swap is a
  planned contingency rather than an emergency
- **New dependencies must state their import cost** in the PR, measured with
  `-X importtime`

## Consequences that are benefits

Keeping the CLI and provider layers thin enough to hit this number also keeps them
thin enough to read, which serves the primary goal. The constraint and the teaching
goal point the same direction, which is unusual and worth exploiting.

## Rejected alternatives

**Treating startup as a nice-to-have** was rejected because it is unrecoverable in
practice. Import graphs get worse monotonically unless something enforces
otherwise, and retrofitting laziness across a finished codebase is far more work
than never allowing the eager import.

**A daemon or persistent server** to amortise startup was rejected in ADR-0005 for
shape reasons, and would be the wrong fix here too.
