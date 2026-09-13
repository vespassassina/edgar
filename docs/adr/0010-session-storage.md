# ADR-0010 — Session storage: JSONL transcripts with SQLite indices

**Status:** Accepted · 2026-09-02 · Resolves OQ-5

## Context

Sessions need to persist for `--resume` and `--continue`, subagent transcripts need
inspecting after the fact, and scheduled runs write transcripts nobody watches live.

## Options

**A. Pure SQLite.** One store, transactional, queryable, no format drift. Opaque to
`grep`, `tail` and `jq`.

**B. Pure JSONL.** Greppable, tailable, diffable, trivially inspectable. No indices,
no transactions, slow to query across sessions.

**C. Hybrid.** JSONL for the transcript, SQLite for state and indices.

## Decision

Option C.

- **Transcript**: append-only JSONL at `.edgar/sessions/<ulid>.jsonl`, one message
  per line
- **State and indices**: SQLite — session metadata, budget, last-run state, cross-
  session search

## Consequences

**The deciding argument is pedagogical.** A reader can run:

```
tail -f .edgar/sessions/01J8X....jsonl | jq -c '{role, blocks: (.content|length)}'
```

and watch an agent session happen live, in a format they already understand. In a
project whose primary purpose is teaching how a harness works, that is worth more
than storage purity. The same command is the fastest debugging tool available when
something goes wrong.

**Append-only is a real safety property.** Compaction produces a *new* revision
rather than rewriting history (ADR-0007, `context/compact.py` returns new
transcripts), so a compaction bug cannot destroy the record of what happened.

**Session IDs are ULIDs**, sortable by creation time, so `ls` is chronological
without a query.

**Consistency risk is accepted and bounded.** The JSONL and the DB can disagree if
the process dies between writes. Mitigation: JSONL is the source of truth for
message content, the DB is a rebuildable index, and `edgar doctor` can reindex from
transcripts.

**Line endings must be explicit.** `newline=""` on all text IO and `\n` written
explicitly, or Windows produces `\r\n` and every downstream `jq` pipeline breaks.

**SQLite needs WAL mode, short transactions and a busy timeout.** Project
directories synced by OneDrive or Dropbox are a known source of lock contention,
and `doctor` warns when it detects one.

## Rejected alternatives

**Pure SQLite** was rejected on inspectability. It is the better engineering answer
for a product and the worse one for a teaching artifact.

**Pure JSONL** was rejected because cross-session memory search and budget
accounting genuinely need indices, and building them over flat files is inventing a
database badly.
