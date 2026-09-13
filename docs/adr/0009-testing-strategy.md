# ADR-0009 — Testing: offline-first, contract suite, scheduled live smoke, evals

**Status:** Accepted · 2026-09-02

## Context

Testing an agent harness is the genuinely interesting engineering problem in this
project, and it is what decides whether the repo is a good learning base or another
agent demo. The core difficulty is nondeterminism: LLM output varies, providers
change under you, and network calls cost money.

## Decision

Four offline layers on every PR, plus scheduled live tests, plus on-demand evals.

### Layer 1 — Fake provider

A scripted provider returning canned responses, including tool calls, multi-tool
turns, errors and cancellation. This is what lets the loop, tool dispatch,
permissions, compaction, subagents and the controller be tested with **zero
network, zero cost, in milliseconds**.

The single highest-leverage piece of test infrastructure in the project. It gets
built in milestone 1, before the real providers.

### Layer 2 — Provider contract suite

**One set of tests every adapter must pass identically.** Streaming, tool calls,
multi-tool turns, errors, cancellation, token accounting, capability declaration.

This is what prevents "works on OpenAI, breaks on Ollama", which is the specific
failure mode ADR-0002's shared adapter invites. A new provider is done when it
passes the contract suite, and that is a meaningful, checkable definition of done.

### Layer 3 — HTTP cassettes

Recorded real exchanges replayed offline. Catches schema drift and real-world
response shapes a hand-written fake will always miss, because a fake encodes what
you *believe* the API does.

### Layer 4 — Property tests

For the parts that are pure functions, which the architecture deliberately
maximises:

- **Compaction pairing invariant**: no `tool_use` is ever orphaned from its
  `tool_result`, for any transcript and any cut point
- **Compaction idempotency**: compacting a compact transcript is a no-op
- **Cron due calculation**: for any schedule, state and clock
- **Path scoping**: no traversal, symlink or UNC input escapes the allowed root
- **Redaction**: no known secret pattern survives a write

### Layer 5 — Scheduled live smoke

A nightly or weekly CI job hitting each provider with repo secrets, opening an
issue on failure.

**Why this is worth the cost:** cassettes go stale **silently**. Without live
tests, the day a provider changes its streaming format you find out from a user's
bug report rather than from CI. That is the wrong way round for a project one
person maintains.

### Layer 6 — Eval set

10 to 20 tasks scored by outcome rather than exact output, run on demand. Catches
prompt and loop regressions that unit tests structurally cannot: a change that
makes the system prompt worse breaks nothing and passes everything.

## Consequences

- **PRs stay fast and free.** Layers 1 to 4 only, target ≤ 60 s [NFR-2]
- **Live failures are isolated** from PR signal, so a provider outage never blocks
  a contributor
- **API keys live in repo secrets** and are used only by the scheduled job, never
  by PR builds, including from forks
- **Evals are explicitly not a gate.** They are slow, flaky and expensive, and
  treating them as blocking would erode trust in the suite
- **The architecture is shaped by testability**, which was a deliberate trade:
  pure functions for policy decisions, due calculation and compaction exist partly
  so they can be tested this way
- **Coverage targets** ≥ 90% branch on `core/`, `tools/`, `permissions/`,
  `context/` [NFR-8]. Not on `cli/`, where terminal rendering has poor
  return on test effort

## Rejected alternatives

**Offline only with manual live testing** was the cheaper option. Rejected because
silent cassette staleness is a real and predictable failure mode, and automating
the detection costs one scheduled workflow.

**Mocking at the HTTP client level only** was rejected: it tests the adapter but
not the loop, and the loop is where the interesting bugs are.
