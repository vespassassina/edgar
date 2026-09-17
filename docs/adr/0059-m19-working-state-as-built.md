# ADR-0059 — M19, working state as built

**Status:** Accepted · 2026-09-17 · Completes M19, the first v2 milestone with
code; implements ADR-0025's pinned working state; lands plan mode and the `todo`
tool, which ADR-0037 moved to v1 and ADR-0053 moved out of 1.0

## Context

M19 is the first milestone since 1.0 to write `src/` code, and it touches the
three places where a mistake is expensive: the permission engine, the loop and
compaction. It adds five things — `@path` attachments, plan mode with the `todo`
tool, `edgar context show`, `edgar sessions compact ID` and
`edgar config show --resolved` — in about 340 lines of code against the v2
budget of 9,500.

Plan mode arrives on its third attempt. [ADR-0037](0037-move-six-features-to-v1.md)
moved it out of Core so Core fit in 5,000 lines; [ADR-0053](0053-what-1-0-actually-ships.md)
moved it out of 1.0 because v1 had 626 lines left for two milestones. Both times
the version being priced was bigger than this one: a plan store, a plan editor,
a second policy layer for "plan mode", and a `todo` tool with add, complete and
reorder verbs. What makes it fit now is that almost all of that turned out to be
unnecessary.

Four decisions could reasonably have gone the other way.

## Options and decisions

**1. How pinned working state is represented so it survives compaction.**
[ADR-0025](0025-working-state.md) says the plan and the todo list are pinned
just above the current turn and survive compaction. It does not say where they
live. (A) A `Message` with `pinned=True` inside `session.transcript`, and every
compaction stage taught to step over it. (B) A `Working` object on the
`Session`, outside the transcript, rendered into a message by the prompt builder
on the way out. **Decided: B.**

A is the obvious reading of "pinned message", and it is the one that breaks
invariant 1. `elide`, `fold` and `rewind` are pure functions over a list of
messages that cut on turn boundaries; a message that must never be cut adds a
special case to each of them, and an index that is right in three places and
wrong in the fourth is exactly how the pairing invariant gets broken by a later
change. With B the transcript contains only what it always contained, so the
stages need no new rule and the invariant holds for working state by
construction rather than by care.

The shape: `context/working.py` holds `Working(plan, todos, plan_mode,
previous_mode)`, `render()` (state to one `Message`) and `place()` (that message
just above the last turn-start user message). `context/builder.py`'s `build()`
calls `place()` last. The block is below the cache breakpoint, because it
changes and the prefix may not (CTX-17), and it is byte-identical between
requests until the state itself changes, which is what the 60-turn test asserts.
One line was needed in `compact()`: its `size()` counts the rendered block, or
every stage under-reads the prompt by however much working state weighs.

The block is `TextBlock(attached=True)` with `meta["via"] = "working"`. Both
matter. `attached=True` puts it on the same footing as an `@path` body: context,
never something a human typed, so it can never reach the learning path (MEM-9).
`via` keeps it out of `turn_starts()`, so compaction and `place()` itself agree
about where a turn begins.

**2. How plan mode's read-only policy is enforced.** (A) A new flag on `Policy`
and a branch in `decide()`. (B) A dynamic guard wrapper that vetoes writes while
a session is planning. (C) Set the session's existing `mode` to `read-only` and
remember what it was. **Decided: C**, which is the conservative option and also
the smallest.

`decide()` is a pure function that is property-tested; a plan-mode branch would
be a second way to express something the mode already expresses, and two ways to
say "read-only" is one way too many. B is worse: a dynamic layer is a place where
a future caller can pass the wrong session and silently get a wider policy.

With C, `enter()` stores `previous_mode` and sets `session.mode = "read-only"`;
`leave()` puts `previous_mode` back. The permission engine is untouched. Three
properties fall out of it, and each has a test:

- A write in plan mode is denied as `permission_denied` by the ordinary
  read-only rules, not by anything plan mode added.
- `leave()` can only restore a mode the session already had, so the widest
  outcome of `/plan` followed by `/go` is the mode the human chose before. A
  second `/plan` does not overwrite `previous_mode`, so two `/plan`s and a `/go`
  cannot leave the session in `read-only` forever, nor widen it.
- `enter()` and `leave()` are reached only from `/plan`, `--plan` and `/go`,
  all typed by a human. No tool, model, subagent or hook can call them, which is
  invariant 2 as a call graph rather than as a check.

`--plan` with `-p` also passes `--mode read-only` through the normal flag path,
so a non-interactive plan run is read-only by the same mechanism, not by
`enter()` alone.

Plan *mode* is deliberately not restored by `--resume`. The plan text and the
todo list come back, because they are context; re-widening a resumed session's
policy is a human's decision and re-tightening a resumed session into read-only
without being asked would be a surprise. The mode a resumed session gets is the
mode its config and flags give it, as before.

**3. The `todo` tool's verbs and category.** (A) `add`, `complete`, `remove`,
`reorder`. (B) One call that replaces the whole list. **Decided: B.** The model
cannot see the list except through what it last wrote, so a diff against it
drifts; a whole list cannot. It is also why the tool is forty lines.

Its category is `read`, which deserves saying out loud because a todo tool
plainly writes something. The category answers "does this change anything the
user owns", and this changes nothing outside the session's own working state.
Two things follow: the verify gate, which only runs after a turn that used a
non-read tool, is not tripped by bookkeeping; and the tool stays callable in
plan mode, where writing the list is the entire work. A `write` category would
have made plan mode unable to plan.

Persistence rides the event bus. `TodoUpdated` is in `RECORDED`, so the event is
the JSONL record and `replay()` rebuilds the list from it; `save_plan()` writes
a `{"type": "plan"}` entry and `sessions/<id>/plan.md`. No second save path, and
nothing new in the loop.

**4. Where `@path` stops, and what it does about control files.**
`context/attach.py` refuses a missing path, a directory, a credential file, a
path outside the working directory and anything that is not decodable text, each
with a sentence naming the path; none of them raises, and the turn does not run.
It does *not* refuse `.edgar/config.toml`. The permission engine asks about a
control file only when a tool would **write** it (PERM-12); a read inside the
working directory is allowed in every mode. Refusing it here would be one module
inventing a rule the engine does not have, and rules that live in two places
disagree eventually. Oversized content goes through `tools/spill.py`, the same
spill as oversized tool output.

The typed line is never rewritten. The file's text leaves `attach()` as a
separate body that the loop wraps as `TextBlock(attached=True)`, so the learning
boundary is a type, as MEM-9 requires, and not a filter over the prompt.

## Consequences

- Compaction gained one line (counting the block) and no new special case. The
  pairing invariant's proof is unchanged.
- The permission engine gained nothing at all. Plan mode is a mode.
- `core/loop.py` is unchanged and still 200/200 lines of code; the REPL's `_run`
  split into `_run` and `_turn` to keep attachment and the plan-saving step
  shallow.
- `core/session.py` now imports `edgar.context.working` at runtime, and
  `context/working.py` imports `Session` only under `TYPE_CHECKING`. `core`
  already imports `context` (`core/loop.py`, `core/aside.py`), so the direction
  is the one the architecture already had.
- A new file, `cli/inspect.py`, holds the three inspection commands rather than
  growing `cli/admin.py`; M22 adds to it.
- `just loc` reads 8,374 of 9,500 after M19 (374 lines of code added against the
  ~340 estimated), with M20–M22 to come.

## Alternatives not taken

A plan *store* (plans as first-class objects with ids, listing and reuse) and a
plan editor were part of the versions ADR-0037 and ADR-0053 priced. Neither is
here. A plan is the answer to a turn taken in plan mode: a pinned block and a
`plan.md` a human can open in an editor they already have. If a later milestone
wants plans to be reusable artefacts, that is a new decision with a new ADR, not
an extension of this one.
