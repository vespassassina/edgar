# ADR-0028 — Input during a turn: queue by default, steer on request, btw on the side

**Status:** Accepted · 2026-09-13 · Replaces CLI-13 ("typing while streaming queues input for the next turn") and moves it from v1 to Core

## Context

A turn can run for minutes. People keep typing while it runs, and they mean one of
three different things:

1. "Do this next." The current turn is fine; this is the following instruction.
2. "Change course." The current turn should take this into account now, without
   being thrown away.
3. "Quick question." Something unrelated to the work, which should not disturb it
   or end up in the transcript.

Harnesses differ on what plain typing means during a turn. Some inject it into the
running turn, some queue it, some interrupt. Getting the default wrong is costly
in both directions: injecting an instruction the user meant for later derails a
turn that was going well; queueing a correction lets the turn continue in the wrong
direction.

What makes steering non-trivial is the pairing invariant (CTX-4): a message cannot
land between an assistant message's tool calls and the tool message holding their
results. Every provider rejects that transcript.

## Options

**A. One behaviour, queue only.** The old CLI-13. Simple, but there is no way to
correct a turn short of cancelling it.

**B. Steer by default.** Responsive, but a "do this next" typed mid-turn silently
changes the current task.

**C. Three explicit verbs, queue as the default.** Plain text queues; `/steer` and
`/btw` are explicit.

## Decision

**C.** While a turn is running in the REPL:

| Input | What happens |
|---|---|
| plain text, or `/queue TEXT` | Held in a FIFO queue. When the turn finishes, each queued entry runs as its own turn, in order |
| `/steer TEXT` | Delivered into the **current** turn at the next safe point, as a user message, and the turn continues |
| `/btw TEXT` | A side question, answered at once by a separate request that runs next to the turn. Neither the question nor the answer enters the transcript |
| `/queue` | Lists the queue |
| `/queue clear` | Empties it |

When no turn is running, plain text, `/queue` and `/steer` all start a turn; `/btw`
still answers on the side. While a permission prompt is open, typed text answers
the prompt.

**Safe points.** A steer is appended only between complete units: after the tool
message that answers the current tool calls, or after an assistant message with no
tool calls. It is never inserted between a call and its result, so the pairing
invariant holds by construction. The loop drains pending steers in one place,
immediately before building the next request. If the model has just finished and a
steer is pending, the loop appends it and sends another request instead of ending
the turn; the verify gate runs only when the model stops and no steer is pending. A
steer is never deferred to the next turn.

**`/btw`.** The side request uses the session's model, the same system prompt and a
snapshot of the transcript cut back to the last complete unit, with the question
appended and **no tools**. It shares the cached prefix, so it is cheap. The answer
is printed as a labelled block between output blocks, never inside a streaming
paragraph, and charged to the session budget. It is recorded in the JSONL as an
`aside` record, not a message, so the record stays complete while the prompt stays
clean.

**Cancellation.** Ctrl-C cancels the turn (CLI-12) and returns queued and
undelivered steered text to the input line, unsent. Cancelling is how a user says
"stop and let me rethink"; auto-running the queue afterwards would ignore that.

**Scope.** Interactive REPL only. A `-p` run has no input channel during the turn.
Steering and asides target the main agent; subagents are not steered. The
embedding API (EXT-9, v1) may expose `steer()` later, through the same safe-point
mechanism.

## Consequences

- The loop gets one extra step: drain pending steers before building the next
  request. The steer arrives from the REPL through the session, so the loop stays
  free of I/O.
- Anthropic's API requires alternating roles, and a steer after a tool message puts
  two user-role messages in a row in its format. The Anthropic adapter merges
  consecutive user-role content into one message (tool results first, then text).
  That is translation, so it lives in the adapter and the canonical transcript is
  unchanged.
- Steered and queued text is typed by a human, so it is a valid learning source
  (MEM-8) like any prompt. A `/btw` answer is model output and is not.
- `/btw` is a model call the user explicitly asked for, so it does not conflict with
  "no hidden calls" (ADR-0023).
- New events, part of the 1.0 format freeze: `InputQueued`, `SteerApplied`,
  `AsideStarted`, `AsideFinished`.

## Rejected alternatives

**Steer by default (B).** Derails turns that were going well, and the user cannot
see that their "next" instruction was absorbed into the current task. What would
change the answer: evidence from use that most mid-turn typing is corrective.

**Interrupt on typing.** Destroys work in progress for what is often a note for
later. Ctrl-C already exists for interrupting.

**`/btw` with tools.** A side question that can read files or run commands is a
second agent sharing the working directory with the first, with all the
concurrency questions that brings. Without tools it is a question about what is
already in context, which is what "by the way" means.
