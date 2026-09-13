# ADR-0007 — Memory: four surfaces, SQLite store, markdown interface

**Status:** Accepted · 2026-09-02

## Context

The brief asks for config, memory, experience tracking and autolearn. Most
harnesses conflate these into one file the agent appends to, and it degrades
predictably.

## The governing principle

**Hand-authored context and machine-learned memory must never share a file.**

If the agent can append to the `AGENTS.md` you maintain by hand, your instructions
and its guesses become indistinguishable, and you stop trusting either. Once you
stop trusting the file you stop reading it, and once you stop reading it the memory
system is dead weight that costs tokens every turn.

## Decision

**Four separate surfaces:**

| Surface | Written by | Storage | Purpose |
|---|---|---|---|
| Instructions | Human only | `AGENTS.md` markdown | Standing directives |
| Transcript | Loop | JSONL | Working context |
| Durable facts | Learner | SQLite, markdown-editable | What was learned |
| Experience | Telemetry | SQLite only | What happened |

**Storage: SQLite as the store, markdown as the interface.**

Facts carry scope, provenance, confidence, status, timestamps and use count, which
is what makes dedup, contradiction detection, decay and eviction possible. Flat
markdown cannot express any of that. But nobody wants to hand-edit a database, so
`memory edit` renders the current set to markdown, opens `$EDITOR`, and writes back
on save.

**Retrieval without embeddings:** a small bounded pinned set injected every turn,
plus a `recall` tool over SQLite FTS5 that the model calls when it needs more.

**Autolearn sources are restricted to three:** user prompts, explicit user
feedback and corrections, and errors or failed tool calls.

**`history.md` is per project, skill or folder.** Append-only, human-readable,
capturing timestamp, prompt, decision, why, tools, files, outcome and cost.

## Consequences

**The source restriction is the security design.** Raw tool output and fetched web
content never reach durable memory. This closes the prompt-injection *persistence*
channel **by construction** rather than by filtering, which is a materially
stronger property than a sanitiser. Layered on top: memory is injected in a tagged
envelope framing it as recorded notes, not instructions [MEM-7].

**No embeddings** keeps startup fast (ADR-0001), adds no dependency, and keeps the
retrieval mechanism visible, which matters more in a teaching repo than recall
quality at small scale.

**History condensing must be out of band.** Prompts over ~200 words get condensed
by a cheap model, but doing it inline adds latency to exactly the prompts that were
already going to be slow. It is queued and flushed at turn end or next tick.
Verbatim text lands in SQLite immediately, so a failed condense call loses nothing:
the markdown view is lossy, the data never is.

**Two risks on `history.md`:**
- A pasted secret in a file that may be committed. Mitigated by a redaction pass on
  write, gitignored by default (OQ-1), and a `--no-history` escape
- Unbounded growth, since every session pays to read it. Mitigated by a size cap
  with archive rotation

**`history distill`** reprocesses the log into candidate facts, closing the loop
between history and memory while keeping history raw and memory curated.

**Contradiction detection** [MEM-10] is required, not optional. Without it, a
corrected fact and its correction coexist and the agent's behaviour becomes
non-deterministic in a way the user cannot diagnose.

**Per-skill `HISTORY.md`** reuses this mechanism for scoped skill notes rather than
inventing a second one.

## Rejected alternatives

**Pure markdown memory** was rejected: it cannot support scoring, dedup or
eviction, and it degrades into an unreviewable append-only blob.

**Pure SQLite with no markdown surface** was rejected: hand-editability is what
keeps the user in the loop, and a memory system the user cannot correct is one they
will disable.

**Learning from tool output** was rejected on security grounds. It is the obvious
richest source, and it is exactly the source an attacker controls.

**Silent autolearn with review-after** and **fully gated approval** were both
considered. The chosen narrowing makes the gate largely unnecessary: prompts,
corrections and errors are all things the user either wrote or witnessed.
