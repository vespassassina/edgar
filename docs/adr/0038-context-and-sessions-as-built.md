# ADR-0038 — Context and sessions as built: records by position, S3 only past the window, three commands to v1

**Status:** Accepted · 2026-09-13 · Refines ADR-0010 (the JSONL record), ADR-0016 (the stages), ADR-0029 (session commands); amends ADR-0037 (what Core keeps)

## Context

M5 built the prompt builder, staged compaction, the JSONL session record,
`--resume`, the session commands, cost caps and the control-file check. Building
them settled several things the Blueprint left open or got slightly wrong, and
the milestone ran into the Core budget: after M5 as specified, Core stood at
4,874 of 5,000 lines, and M6 needs about 200.

## Options

**Budget.** (A) Trim docstrings until it fits: cheap, but the docstrings are the
part a reader of "an afternoon" reads first. (B) Move the features ADR-0037 already
named as next candidates, `/history` and `edgar context show`, plus `edgar cost`,
which only sums across sessions and belongs beside the daily cap that does the
same in M7. (C) Raise the budget: ruled out by the maintainer.

**Compaction records.** (A) `replaces: [message ids]`, as the Blueprint sketched:
needs an id on every message, which `Message` does not have and nothing else
needs. (B) `upto: N`, the position of the cut in the view at that moment: replay
rebuilds the same view in the same order, so the position is exact.

**S3.** (A) As sketched: S3 runs whenever the prompt is still over `compact_to`.
In a session whose recent turns alone exceed the target, that elides inside the
recent turns on every request. (B) S3 runs only when the prompt does not fit the
window at all; between the target and the window the prompt is sent as is.

## Decision

**Budget (B).** Simplify first: collapsing arguments that were split one per
line only because of a trailing comma gave 17 lines with nothing lost. Then three
commands move to v1:

| Feature | Requirement | To |
|---|---|---|
| `/history` | CLI-25 (that part) | M7, beside session search; `edgar sessions show ID` prints the same record meanwhile |
| `edgar cost` | BUD-6 (that part) | M7, beside the daily cap; `/cost` and `edgar sessions list` show cost meanwhile |
| `edgar context show` | CTX-2 | M11, beside `edgar doctor`; `edgar prompt show` prints the prefix meanwhile |

Core ends M5 at 4,806 lines, leaving 194 for M6.

**The record** (`.edgar/sessions/<id>.jsonl`, with a `.gitignore` of `*` in the
folder):

- The first line is `{"type": "session", "id", "cwd", "model", "at"}`.
- `message` lines carry `role`, `meta` and `content`, each block tagged with its
  class name as `kind` (`TextBlock`, `ToolUseBlock`, …), so a reader of the file
  sees the names the code uses.
- `compaction` lines carry `stage` (`S1`, `S2`, `S3`), `upto` and, for S2, the
  `summary`. `reset`, `undo` (`turns`, and the `files` its turns changed, for
  the reader), `title`, `model` and `control` (`changed`) lines follow ADR-0029.
- `event` lines keep what a reader needs later: `PermissionResolved` (the audit
  trail, PERM-10), `TurnFinished` with its cost, `AsideStarted`/`AsideFinished`
  (skipped by replay) and `Compacted`, from the main agent only.
- Lines are written with `newline=""` and an explicit `\n`, so the file is the
  same on Windows.

**Compaction.** The usable window is the context window less the output reserve,
and the reserve never takes more than half the window. S1 runs on turns older than
`keep_last_turns` and never drops thinking from the turn in progress (providers
reject a changed reasoning block mid-turn). S2 runs when the prompt is still over
`compact_to`, or on `/compact`, and only if there is something older than the kept
turns other than the summary itself, so a summary is never re-summarised alone.
S3 (B) runs only past the window and elides everything but the last unit; if that
still does not fit, `ContextOverflow` with a hint naming `/compact` and
`context.keep_last_turns`. A compaction that changes nothing records and emits
nothing. CTX-8 is reworded to match: compacting twice changes nothing the second
time, and the prompt ends below `compact_to` unless the kept turns alone are
larger, in which case it ends inside the window.

**Pinned content** lives in `context/builder.py` rather than a `pins.py`: the
personality file, then instruction files from the project and then from
`~/.edgar/`, each introduced by where it came from, joined to the system prompt as
one system message built once per runtime. Tool schemas travel in the request's
own tools field. A personality file over 500 tokens warns at session start.

**Cost caps.** A cap reached ends the turn with reason `budget_exceeded`, not an
exception: the transcript is sealed, the partial result is printed, `-p` exits 6.
The loop checks before each request, so a cap is never overshot by more than one
response. With a cap set, a response of unknown price counts as over it [BUD-5].

**Resume.** `--resume ID` takes a whole id or a unique start of one; `--resume`
alone and `--continue` take the latest. The session keeps its model unless
`--model` is given on the command line; the permission mode is always the one the
current run was started with. A resumed REPL prints the conversation first.

**The control-file check** [PERM-12] compares digests taken when the session
began with those when it ended, and records the difference; the next session
warns. Comparing within a session, not across sessions, means a human editing
`AGENTS.md` between sessions is not warned about their own edit.

**CTX-10** (`edgar sessions compact`, a Should) was not built; it stays v1 as
the requirement map already says.

## Consequences

- Records address the view by position, so the view must never be reordered or
  filtered outside `apply()`. Load-bearing: a change to `elide`, `fold` or
  `rewind` that is not a pure function of the view and the cut breaks replay of
  every stored session. `tests/property/test_compaction.py` guards it.
- The block `kind` is a class name, so renaming a content block class is a
  format change and needs a reader for the old name.
- A prompt between `compact_to` and the window with nothing old left to fold is
  sent uncompacted, and the cache holds; the cost is a larger prompt than the
  target, which the status line shows.
- M6 has 194 lines. If it runs over, the next candidates are `/sessions` (the
  CLI's `edgar sessions list` covers it) and the personality warning.

## Rejected alternatives

- **Message ids for `replaces`.** Worth revisiting if v1's fork (CLI-22) or
  session search needs to point at a message from outside its session.
- **S3 at the target.** Revisit if providers start charging for cache misses
  steeply enough that a larger prompt costs more than a re-elided one.
- **A cross-session control hash.** It would warn about a human's own edits,
  which teaches people to ignore the warning.
