# ADR-0011 — Event bus for all output

**Status:** Accepted · 2026-09-02

## Context

The same turn loop has to serve four very different consumers: an interactive REPL
with a live status bar, a piped one-shot writing plain text to stdout, a subagent
whose output is a row in the parent's status bar, and a scheduled run with no
observer at all.

The naive approach threads a "printer" or a set of callbacks through the loop,
tools and providers. That couples the loop to presentation and makes the
`-p --json` path drag terminal rendering code into the import graph, which fights
the startup budget from ADR-0001.

## Decision

A synchronous in-process event bus. The loop, providers and tools **emit**;
consumers **subscribe**.

```
loop / provider / tool  ──emit──▶  EventBus  ──▶  status bar (stderr, TTY only)
                                             ──▶  renderer (stdout)
                                             ──▶  telemetry (SQLite)
                                             ──▶  logger (file)
                                             ──▶  parent status row (subagents)
```

Roughly 40 lines. No queues, no threads, no async dispatch. Subscribers needing
async work queue it themselves.

Every event carries an agent id and depth, so a subagent's events route to the
right status row without the loop knowing a status bar exists.

## Consequences

- **The loop has no idea how output is presented**, which is why the same code
  path serves interactive, piped, subagent and scheduled execution
- **NFR-1 is achievable**: on the `-p --json` path, no rendering subscriber is
  attached, so `rich` is never imported
- **The status bar becomes trivial to make multi-row** for parallel subagents
  (ADR-0006), because concurrency is already expressed in the event stream
- **Telemetry is a subscriber, not an instrumentation concern**, so
  `memory/experience.py` contains no calls sprinkled through the loop
- **Tests attach a recording subscriber** and assert on the event sequence, which
  turns out to be the clearest way to test loop behaviour: a test can state
  "proposed, permission asked, allowed, started, finished" as a literal list
- **Synchronous dispatch means a slow subscriber blocks the loop.** Accepted:
  subscribers are required to be fast, and the ones that are not (telemetry writes,
  history condensing) queue internally

## Rejected alternatives

**Callback parameters** threaded through function signatures were rejected for
coupling and signature noise.

**An async bus with queues** was rejected as premature. It buys nothing at this
scale and adds an ordering problem where events could arrive out of sequence,
which would make the status bar lie.

**Logging as the event mechanism** was rejected: log records are strings shaped for
humans, and the status bar and telemetry need structured data.
