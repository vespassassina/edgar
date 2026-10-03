# ADR-0074 — Consecutive read-only calls run at the same time

**Status:** Accepted · 2026-10-03 · Amends TOOL-12, supersedes the first item of PRD §5.3

## Context

A model that wants five files asks for five `read` calls in one response. edgar
ran them one after another. Claude Code runs them together, and the wait shows,
mostly on slow tools: an HTTP tool, an MCP server, a big `grep`.

## Decision

- In `execute_many`, a run of consecutive calls whose tool counts as a read
  (`permissions.policy.category() == "read"`) is one group and runs concurrently,
  at most `READ_PARALLEL` (8) at once. Results still come back in call order.
- `task` runs keep their own group and their own `max_parallel` cap. A read and
  a task never share a group, because a subagent may write.
- Anything else (write, shell, network, memory) runs alone, in order, and ends a
  group. A call to an unknown tool runs alone.
- `todo` says `category="read"` but writes the session's list, so it is excluded
  by name: its order matters.
- The system prompt now says so, and tells the model to batch independent reads.

## Consequences

- Permission prompts for reads still go through the guard's one lock, so two
  prompts never show at once.
- A read cannot see a write from the same response, because a write ends the
  group and runs after the reads before it, as before.
- Tainting is applied after the group, so a network read inside a group cannot
  taint its siblings. It taints everything after the group, as before.
- A read-only HTTP tool is a "network" category tool, not a "read", so it is not
  fanned out. That is a deliberate first cut; widening it is a later ADR.
- Cost: about 25 lines of code in `tools/execute.py`.
