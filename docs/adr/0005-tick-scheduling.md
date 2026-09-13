# ADR-0005 — Tick model for scheduling

**Status:** Accepted · 2026-09-02

## Context

Scheduled and self-triggered runs are wanted. Cron, launchd and Task Scheduler
already solve "run this at a time", and a CLI that ships its own scheduling daemon
is usually doing the wrong job.

## Options

**A. Emit-only.** `schedule add` writes directly into crontab, launchd plists or
`schtasks`. Three platform backends to write and test, and the scheduling logic
ends up living outside the project where it cannot be reasoned about or tested.

**B. Built-in daemon.** Long-running process, supervision, PID files, log rotation.
Still needs a host entry to survive a reboot, so it adds a component without
removing one. Wrong shape for a unix tool.

**C. Tick.** Schedules declared in a file the user edits. One `edgar tick` command
computes what is due and runs it. Exactly one host scheduler entry per machine,
installed by a helper, calling `tick` every minute.

## Decision

Option C, plus agent self-scheduling.

```
host scheduler (1 entry, every minute) → edgar tick → due.py (pure) → run
```

```python
def compute_due(
    schedules: list[Schedule],
    state: dict[str, RunState],
    now: datetime,
) -> list[Schedule]: ...
```

`edgar install-tick` writes the single host entry per platform. `schedule_self` is
a tool that lets a running agent queue its own future run.

## Consequences

**The reason this was chosen:** due calculation, cron parsing, overlap prevention,
catch-up-after-sleep policy and jitter all become **pure functions**, testable
exhaustively with a frozen clock, no subprocess, no network, no waiting. For a
project whose test strategy is the interesting part, this matters more than the
scheduling feature itself.

**One integration point per OS** instead of three schedulers, and the platform code
is confined to `install.py`.

**Catch-up policy must be explicit** [SCH-7]: a laptop that was asleep for six
hours has several missed runs, and `skip` / `once` / `all` are all legitimate
answers depending on the job. Silently picking one is wrong.

**Overlap prevention is required** [SCH-6]. A minute-granularity tick will fire
again while a long run is still going.

**Scheduled runs are non-interactive**, which means each entry carries its own
mode and allowlist (ADR-0004). Output routing needs a home: a transcript per run in
`.edgar/runs/`, plus an `on_complete` shell hook.

**Notifications are deliberately out of scope for v1.** The `on_complete` hook lets
users wire their own notifier, and desktop/Teams/webhook notifications go on the
roadmap rather than into the core.

**Self-scheduling needs guardrails** [SCH-11]: rate limits, a cap on pending
entries, and a depth guard, or a self-rescheduling agent runs away.

## Rejected alternatives

**Emit-only** was rejected for testability, which is the same reason tick was
chosen rather than a general preference for indirection.

**Daemon** was rejected for shape. A tool that composes with pipes should not also
be a service.
