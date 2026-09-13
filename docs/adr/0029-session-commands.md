# ADR-0029 — Session commands: append-only, rewind the conversation not the disk, no hidden titles

**Status:** Accepted · 2026-09-13 · Extends CLI-14; `/resume` changes meaning (session restore becomes `/load`)

## Context

The REPL needs the commands people expect from a daily driver: start over, go
back, try again, pause, see where things stand, switch model, find and reopen old
sessions. Each one touches a design rule already in place:

- The session record is append-only JSONL, never rewritten (ADR-0010, CTX-14).
- The transcript must satisfy the pairing invariant at every moment (CTX-4).
- No model call or host the user did not ask for (ADR-0023). The field review
  found users angry that a harness generated session titles with a hosted model
  they never configured.
- Tools change files. The conversation can be rewound; the disk cannot, not without
  a snapshot mechanism edgar does not have.

## Decision

**Commands and their meaning.**

| Command | What it does | Tier |
|---|---|---|
| `/new` | Start a new session. The current one stays on disk | Core (M5) |
| `/clear` | Clear the screen, then `/new` | Core (M5) |
| `/reset` | Same session, empty conversation. Model, mode, title and working state stay | Core (M5) |
| `/history` | Print this session's full conversation from the record, compacted parts included | Core (M5) |
| `/undo [N]` | Rewind the last N prompts (default 1) and continue from there | Core (M5) |
| `/retry` | `/undo 1`, then send the same prompt again | Core (M5) |
| `/title [TEXT]` | Show or set the session title | Core (M5) |
| `/sessions` | List sessions: id, title, date, turns, cost | Core (M5) |
| `/load ID\|PATH` | Open a session by id, or a file written by `/save` | Core (M5) |
| `/save [PATH]` | Export this session as one portable JSONL file, blobs inlined, that `/load` and `edgar --load` accept | Core (M5) |
| `/stop` | Cancel the current turn; the same as one Ctrl-C (CLI-12) | Core (M4) |
| `/pause` | Hold the current turn at the next safe point, between units | Core (M4) |
| `/resume` | Continue a paused turn | Core (M4) |
| `/status` | Session id and title, model, mode, context use, cost, queue, pending steers, paused, taint, trust, verify command | Core (M4) |
| `/model [NAME]` | Without a name, list the configured models; with one, switch for the rest of the session | Core (M4) |
| `/init` | The same scaffolding as `edgar init` (CFG-4) | v1 (M11) |
| `/browser` | Connect the browser MCP server configured under `[browser]` | v1 (M8) |

**Everything is a record, nothing is rewritten.** `/reset`, `/undo`, `/title` and
a `/model` switch append a line to the session JSONL (`reset`, `undo`, `title`,
`model`). Replay applies them, so `--resume` and `/load` rebuild exactly what the
user saw. The full history, including undone turns, stays on disk and in session
search. `/history` reads the record, not the prompt.

**Undo works on turns, and turns are whole units.** A turn is a user prompt and
everything up to the next prompt, so undoing one never splits a tool call from its
result.

**Rewinding the conversation does not rewind the disk.** `/undo` and `/retry` print
the files that `write` and `edit` changed in the undone turns, from the tool
records, and do not revert them. Reverting reliably needs snapshots, and a git
stash or a copy is wrong in enough cases (untracked files, large trees, files the
user edited meanwhile) that doing it silently would be worse than saying so.
Checkpoints are an open question (OQ-10).

**Pause holds at a safe point.** `/pause` sets a flag the loop checks where it
drains steers: after the current request or tool call completes, before the next
request. Nothing is cancelled. While paused, the user can inspect (`/status`,
`/history`), steer, queue or `/btw`. `/resume` continues; `/stop` cancels.

**Titles never cost a model call.** The default title is the first line of the
first prompt, trimmed to 60 characters. `/title TEXT` replaces it. No model is
asked, ever, so no request goes anywhere the user did not choose.

**`/model` switches are announced and recorded.** A switch emits `ModelSelected`
with rule `user`, writes a `model` record, and follows the reasoning rules for a
family change (PRV-13: foreign reasoning is dropped, not rewritten). The cached
prefix is rebuilt once, and `/status` says so.

**`/browser` is an MCP preset, not a new tool kind.** Browser automation comes from
an MCP server the user configures (Playwright MCP, Chrome DevTools MCP or another)
under `[browser]`. `/browser` spawns it on demand, loads its tools with deferred
schemas (TOOL-15), and marks their output untrusted, which taints the session
(PERM-11). With no `[browser]` block, it prints the configuration to add and does
nothing else: edgar never downloads or starts a package the user did not name.

**`/resume` changes meaning.** It pairs with `/pause`. Reopening an old session is
`/load` in the REPL; the `--resume` and `--continue` flags keep their meaning
(CLI-11).

## Consequences

- New JSONL record types: `reset`, `undo`, `title`, `model`. New events: `Paused`,
  `Resumed`, `TurnsUndone`.
- `/undo` is honest about its limit. People who want file rollback use git, and the
  list of touched files tells them where to look.
- `/save` output is self-contained, so a session can move between machines or be
  attached to a bug report. It can contain secrets that appeared in tool output;
  `/save` says so, and applies the same secret redaction as observations (MEM-15).
- `/browser` inherits every MCP safeguard: trust for project config (PERM-13),
  deferred schemas, taint.

## Rejected alternatives

**`/undo` that reverts files through git.** Correct only when the tree was clean
and tracked, and destructive when it was not. What would change the answer: a
snapshot mechanism that handles untracked and user-edited files, which OQ-10 asks
about.

**Model-generated titles.** Better titles, at the cost of a model call per session
that the user never asked for. Titles are cheap to set by hand.

**A built-in browser tool.** A browser engine is a heavy dependency and a large
attack surface in core. MCP servers for browsers exist and improve independently.
