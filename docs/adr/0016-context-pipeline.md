# ADR-0016 — Context is compressed in stages, cheapest first, on whole units

**Status:** Accepted · 2026-09-13 · Amends CTX-1, CTX-3, CTX-4, CTX-5, TOOL-4

## Context

The v0.2 compaction design had one mechanism: find a safe cut point and summarise
everything before it with a cheap model. Review found three problems.

**The pairing invariant was too weak.** It required each `tool_result` to appear
somewhere after its `tool_use`. Providers require more: OpenAI wants the tool
messages *immediately* after the assistant message that called them, and Anthropic
wants the results in the very next user message. A compaction that put a summary
between a call and its result passed the property test and still got a 400.
Anthropic also rejects a tool-use turn whose thinking block was altered.

**It had no answer when the pinned content alone was too big.** With four pinned
turns and one 60k-token tool result inside them, there is nothing compactable left
and the algorithm has no defined behaviour. The idempotency property test would
find this on its first run.

**It used a model call for work that needs none.** In tool-heavy sessions most of
the context is old tool output the model has already acted on. Removing it needs a
rule, not a summary.

## Options

**A. Keep summarise-only**, strengthen the invariant, add an overflow error.
Smallest change. Every compaction costs a model call and loses detail that a
deterministic step would have kept.

**B. Staged pipeline.** Deterministic stages first, a model call only when they are
not enough, all operating on whole units so pairing holds by construction.

**C. Sliding window.** Drop the oldest turns with no summary. Cheapest. Loses the
goal and earlier decisions, which is how agents start repeating themselves.

## Decision

Option B.

**The unit.** Compaction never sees individual blocks. It sees units:

- a message with no `ToolUseBlock`, or
- an assistant message with one or more `ToolUseBlock`s **plus the tool message
  immediately after it**, whose `ToolResultBlock`s match those ids one-to-one

A turn is the sequence of units from a user message to the assistant message that
ends without tool calls. Stages remove, stub or summarise whole units and whole
turns only. That is what makes the invariant hold by construction instead of by
retry.

**The strengthened invariant** [CTX-4]: every assistant message containing tool
calls is immediately followed by exactly one tool message, and the result ids in it
equal the call ids. Thinking blocks inside the turn in progress are never altered.

**The stages**, run in order until the prompt is under target:

| Stage | Where | Cost | What it does |
|---|---|---|---|
| **S0 Spill** | at tool execution, every call | none | Output over `tools.max_output_tokens` is head/tail truncated with a marker. The full output is written to `.edgar/sessions/<id>/blobs/<tool_use_id>.txt`, and the marker names that path so the model can `read` it with an offset [TOOL-4, CTX-13] |
| **S1 Elide** | when over `context.compact_at` | none | For turns older than `context.keep_last_turns`, replace each tool result's content with a one-line stub (tool, argument preview, original size, blob path). Drop thinking blocks from completed turns. The blocks stay, so pairing is untouched |
| **S2 Summarise** | if still over | one cheap-model call | Replace the oldest completed turns with one rolling summary message of fixed shape: *Goal*, *Decisions*, *Files touched*, *Open threads*, *Errors seen*, *Blobs worth re-reading*. A previous summary is folded into the new one, so there is at most one |
| **S3 Overflow** | if the pinned content alone is over | none | Elide inside the pinned recent turns, except the unit in progress. If still over, raise `ContextOverflow` with a hint: `/compact`, lower `keep_last_turns`, or a larger-context model. The user's current input is never dropped silently |

**Hysteresis.** Compaction starts at `context.compact_at` (default 0.70 of the
usable window) and works down to `context.compact_to` (default 0.50). Without that
gap a long session compacts on every request, which also destroys the prompt cache
on every request.

**Assembly order**, most stable first so the cache prefix survives [CTX-1]:

```
system prompt · tool schemas · instructions (AGENTS.md …) · pinned facts · skill index
── cache breakpoint ──────────────────────────────────────────────────────────────
rolling summary · transcript (compaction works here only) · current turn
```

Pinned facts and the skill index are computed once at session start and frozen
(MEM-6), so nothing above the breakpoint changes during a session.

**Compress the prompt, never the record.** The JSONL transcript is append-only. A
compaction appends a `compaction` record naming the unit range it replaced and the
summary text, so `--resume` rebuilds the compacted view and the full history stays
on disk. Session search (MEM-20) runs over the full record, which makes elided
material findable again.

## Consequences

- **Pairing holds by construction.** Stages operate on units, so the
  widen-and-retry loop from v0.2 becomes an assertion, not an algorithm
- **Most compactions cost nothing.** S1 alone typically recovers most of the window
  in tool-heavy sessions, and the model call in S2 is the exception
- **Idempotency is simple to state and test:** after any compaction the prompt is
  below `compact_to`, which is below `compact_at`, so a second call is a no-op.
  Overflow raises on both calls
- **Spill turns truncation from lossy to lazy.** The model can recover anything it
  needs from a blob with `read`. Blobs live under `sessions/`, which is
  machine-owned and gitignored
- **The summary is transcript, not memory.** It may be shaped by tool output, and
  that is acceptable because it lives and dies with the session. It never feeds the
  learner (ADR-0017)
- **Load-bearing:** nothing may split a unit. A future "smarter" compaction that
  trims inside a unit reopens the 400 class of bugs

**Other places context is kept small**, recorded here so they are seen as one design:
subagents return summaries rather than transcripts (the most effective compression
there is), skills show only name and description until loaded, facts beyond the
pinned cap are reached through `recall` rather than injected, and the pinned set is
bounded with its capacity shown in the envelope header (MEM-7).

## Rejected alternatives

**A (summarise-only)** is rejected because it pays a model call to remove content
the model has already consumed, and loses detail a stub would have pointed to.

**C (sliding window)** is rejected because the goal and early decisions are exactly
what falls off first. It remains the behaviour of S3 in spirit, but only after
everything cheaper has run and with a loud error rather than silent loss.

**Embedding-based selection of old turns** is out of scope for the same reason as
ADR-0007: it hides the mechanism. Revisit only if FTS over the record proves
insufficient for real sessions.
