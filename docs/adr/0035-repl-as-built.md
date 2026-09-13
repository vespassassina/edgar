# ADR-0035 — The REPL as built: a prompt that never blocks, text a line at a time, no rich

**Status:** Accepted · 2026-09-13 · Refines ADR-0028 and BLUEPRINT §4.3, §13, §16; lands in M4

## Context

M4 had to make three requirements hold together: input is accepted while a turn
runs (CLI-13), output stays in the terminal's own scrollback with only the status
line redrawn (CLI-23, OQ-4), and the size budget holds (M4 started with 2,409 of
5,000 Core lines). The Blueprint assumed `rich` for Markdown and the status bar,
and `prompt_toolkit` for input.

The difficulty: a prompt that stays open at the bottom of the screen and text that
streams above it both need the terminal's last line. Streaming a partial line above
an open prompt breaks the line on every token, and rendering Markdown means
redrawing text already printed. Both break CLI-23.

## Decision

- **prompt_toolkit owns the bottom of the screen.** One `PromptSession` stays open
  for the whole session. `patch_stdout` prints everything else above it, and the
  status line is its bottom toolbar, refreshed ten times a second from the
  `Status` subscriber. On Windows, prompt_toolkit drives the console itself.
- **Text streams a line at a time.** `Printer` emits whole lines, wrapped at the
  last space that fits the terminal width, so a long paragraph still appears as it
  is written. A block that must not interrupt a line (a `/btw` answer, a notice)
  waits for the line to end.
- **No Markdown rendering, and no `rich`.** Model output is Markdown and reads
  fine as written; rendering it would mean redrawing it. `rich` leaves the
  dependency list (BLUEPRINT §16), one fewer dependency on the interactive path.
- **`Shell` holds the logic; `interact()` holds the terminal.** The queue,
  `/steer`, `/btw`, `/stop`, `/pause` and the slash commands are methods on a
  plain class that tests drive with the fake provider, without a terminal. The
  prompt_toolkit wiring is one function with one test that sends real keystrokes.
- **Cancel is asyncio's cancel, sealed by the loop.** Ctrl-C and `/stop` cancel
  the task running the turn. `run_turn` catches the `CancelledError`, seals the
  transcript (`core/cancel.py`), emits `TurnFinished(reason="cancelled")` and
  re-raises. Tool results already in when the cancel lands are kept; missing ones
  say "cancelled by user". Text already streamed is kept with
  `meta["interrupted"]`. With `-p`, Ctrl-C does the same and exits 7.
- **The REPL needs a terminal on both stdin and stdout.** Otherwise it is a usage
  error naming `-p` (CLI-4). In the REPL the terminal is one surface, so the
  stdout/stderr split (CLI-5) is enforced where it matters: under `-p`, where
  stdout carries only the result, the JSON or the event stream.
- **Input history** is kept in `~/.edgar/history`, as shells keep theirs. It holds
  what you typed and nothing the model wrote.
- **Not yet persistent.** `/new` and `/clear` start a fresh in-memory session.
  Sessions reach disk in M5, and so do the commands that depend on the record
  (`/reset`, `/undo`, `/history`, `/load`, `/save`). Those say so when typed.

## Consequences

- `TurnFinished.reason` is `completed` or `cancelled`. Callers of `run_turn` see a
  `CancelledError` after the transcript has been sealed, never before.
- A permission prompt (M3) is a question asked through the same `PromptSession`
  (`Shell.ask`), so there is one prompt queue, as TOOL-12 requires.
- M4 took about 950 lines, leaving 1,647 of the Core budget for M3, M5 and M6. That
  is tight: M3 must reuse `execute`'s pipeline for command and HTTP tools, M5
  must keep compaction to the stages already specified, and anything that does
  not fit moves to v1 rather than stretching the budget.

## Rejected alternatives

**`rich.Live` for streaming Markdown.** It redraws the region it owns, which is
exactly what CLI-23 rules out, and it breaks scrollback on long answers.

**Printing partial lines above the prompt.** prompt_toolkit redraws the prompt
after every write; each token then lands on a line of its own.

**A full-screen TUI.** OQ-4 settled that: flicker, broken scrollback, text that
cannot be selected.
