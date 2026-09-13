# ADR-0025 — Plans, todos and forks are session state, not prompts

**Status:** Accepted · 2026-09-13

## Context

Among working practices, planning before executing and keeping a live todo list
come up as the most effective (docs/research/hn-2026-09.md). Users keep `plan.md`,
changelog and working-memory files by hand, because the built-in versions in other
harnesses do not survive compaction or a new session. Others ask for trees: fork a
conversation, try a side path, keep only what worked.

edgar v0.3 had none of these. Its compaction (ADR-0016) could summarise a plan away
like any other text.

## Options

**A. Leave it to skills and instruction files.** No harness change. The plan is
text in the transcript and gets compacted.

**B. Make working state first-class**: a todo list and a plan stored as session
state, pinned above the transcript, and forks built on the JSONL format.

## Decision

Option B.

**`todo` tool** (Core) [TOOL-14]. One call replaces the whole list:
`todo(items=[{text, status}])` with status `pending`, `in_progress` or `done`.
Full-list replacement keeps the tool trivial and the state unambiguous. The list is
rendered in the status line and emitted as `TodoUpdated`.

**Plan mode** (Core) [CLI-20]. `/plan` in the REPL, or `--plan` with `-p`, runs the
turn in `read-only` mode and asks for a plan, which is written to
`sessions/<id>/plan.md`. `/go` leaves plan mode and continues in the previous mode
with the plan pinned. Plan mode is a mode plus a pinned file, not a second engine.

**Working state is pinned** [CTX-18]. The plan and the current todo list are
rendered in one block just above the current turn: below the cache breakpoint,
because they change, and outside the compactable transcript, because they must
survive. Each update is recorded in the JSONL, so `--resume` restores them.

**Forks** (v1) [CLI-22]. `/fork` in the REPL, or `edgar --fork ID[@TURN]`, starts a
new session whose JSONL begins with a `fork` record naming the parent session and
turn. The parent's messages up to that turn are replayed, not copied, so a fork
costs one line. The status line and `sessions list` show the lineage.

## Consequences

- **Compaction never loses the plan,** and the S2 summary no longer has to carry it
- **Small models benefit most:** a todo list re-rendered above the current turn is
  a strong anchor for models that drift on long tasks
- **Forks are nearly free** because the transcript is append-only JSONL
  (ADR-0010). Session branching moves from "past v2" into v1
- **Load-bearing:** working state sits below the cache breakpoint. Putting the
  todo list in the system prompt would break the prefix on every update
  (ADR-0023)

## Rejected alternatives

**A (skills and files only)** is rejected because the plan must survive
compaction, which only the harness can guarantee.

**A structured task graph with dependencies** (as in Beads) was considered. It is
useful for multi-session projects and belongs in an extension or an MCP server; a
flat list covers the turn-level need at a fraction of the size.
