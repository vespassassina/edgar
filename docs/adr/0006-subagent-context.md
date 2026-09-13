# ADR-0006 — Subagents: fresh context, parallel from v1

**Status:** Accepted · 2026-09-02

## Context

"Launch sub agents, use different models for different scopes" is a core
requirement. Two decisions shape everything downstream: what context a subagent
inherits, and whether they run concurrently.

## Options

**Context.** *Fresh* means the subagent sees only its system prompt and the task
description the parent wrote. Cheaper, isolates cleanly, and forces the parent to
write a good task spec, which is most of what makes subagents work at all. The
failure mode is a parent under-specifying and the subagent flailing.
*Inherited* fixes under-specification and destroys the main benefit, since context
isolation is the entire reason subagents exist.

**Concurrency.** *Sequential* is simple and the status bar is trivial. *Parallel*
is where the leverage lives: three explorations at once rather than one after
another. It costs interleaved output, a multi-row status bar, harder cancellation
and harder tests.

## Decision

**Fresh context. Parallel from v1.** Summary returns, not transcripts.

Subagents are **markdown files with YAML frontmatter**, discovered at project then
user level, carrying name, description, model, tool allowlist, mode, budget and
system prompt. That is what delivers "different models for different scopes"
declaratively, with no Python written.

```markdown
---
name: explorer
model: ollama/qwen3
tools: [read, ls, glob, grep]
mode: read-only
budget: { cost: 0.10 }
---
You explore codebases and report findings concisely.
```

**A subagent is the same loop**, re-entered with a different config, a fresh
transcript and a narrowed policy. There is no separate subagent engine.

## Consequences

- **One loop to understand and test.** The `task` tool re-enters `core/loop.py`
- **Permissions may only narrow** relative to the parent [PERM-8]
- **Budget inherits from the parent's remainder**; exhaustion returns a *partial
  result flagged as such* rather than killing the run [SUB-7]
- **Failures surface as tool errors**, so the parent decides what to do [SUB-8]
- **Depth ceiling and cycle detection** are mandatory [SUB-6, SUB-10]. Recursive
  subagent spawning is a real financial risk, not a theoretical one
- **The status bar must render concurrent rows** [SUB-9], which is why the event
  bus (ADR-0011) carries a subagent id on every event
- **Async internals were needed anyway** for streaming and cancellation, so
  parallel fan-out is incremental complexity rather than a new axis
- **Full transcripts are persisted** even though only summaries return, so a
  subagent's reasoning can be inspected after the fact [SUB-4]

## Rejected alternatives

**Sequential in v1 with parallel later** was the safer recommendation and was
overridden deliberately. The judgement: a harness that cannot fan out feels dated
in 2026, and retrofitting a multi-row status bar and concurrent cancellation later
is more disruptive than building for it now.

**Configurable inheritance per subagent** was rejected as premature knobs. If a
real need for inherited context emerges, it can be added as frontmatter without
breaking anything.
