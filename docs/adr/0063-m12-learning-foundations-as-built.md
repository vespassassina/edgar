# ADR-0063: M12, learning foundations, as built

- Status: accepted
- Date: 2026-09-17
- Supersedes nothing. Implements [ADR-0017](0017-learning-boundary.md) and the
  M12 row of [`docs/ROADMAP.md`](../ROADMAP.md).

## Context

M12 opens v3. It is the first code in `edgar.learning`, and the first code in the
project that writes to memory without a human asking it to. ADR-0017 fixed the
rule two years of this design have been built around: *an active fact can only
come from text a human typed, or from an error classification the harness
computed itself.* This ADR records how that rule was actually implemented, and
the four decisions a reasonable person could have made differently.

## Decision

### 1. The boundary is a subscription, not a check

`Learner.__call__` returns unless the event is a `PromptTyped` at depth 0. There
is no filtering, no classifier, no allowlist of phrasings. ADR-0017's option A
(give the learner everything, reject what looks unsafe) was rejected there and
stays rejected: a content filter is a guess about text an attacker can rewrite.

What makes the type check sufficient is that `PromptTyped` is constructed at
exactly two sites — `cli/repl.py`'s `submit()` and `cli/oneshot.py`'s
`run_prompt()` — each from the bare typed string, and both *before* `attach()`
runs. Every excluded source travels a different road and arrives in a different
type: piped stdin is `run_prompt(attached=…)`, an `@path` body is
`Attached.bodies`, tool output is a `ToolResultBlock`, model text is a
`TextDelta`. None of them can become a `PromptTyped`, so there is nothing to
filter.

**The depth check was not in the first draft.** The property test generated a
subagent emitting a prompt, and it became an active fact. That is correct for a
typed line and wrong here: a subagent's prompt is the `task` tool's argument,
which the model wrote. Fixed in `learner.py`, with a unit test and a paragraph on
the tour page, because the mistake is more instructive than the fix.

### 2. Errors are templated, never quoted

`ToolFinished` gained `error: ErrorRecord | None`. The record is the four fields
the harness computed about itself (`tool`, `kind`, `exit_code`, `program`); the
failure's own text stays in the `ToolResultBlock`, goes back to the model, and is
never durable. `error_facts.py` fills a sentence it owns from those fields, so no
byte an attacker wrote reaches a fact — with one exception, named here because it
is the only one: `program` is a basename the model chose. It is safe because
`UNSAFE` strips it to `[A-Za-z0-9._-]`, and the property test generates programs
full of shell metacharacters to prove it.

`REPEATS = 3` is an opinion. Twice is a model retrying inside one turn; three
times across sessions is the project telling you something. `validation`,
`cancelled` and `provider_http` are excluded: they are facts about the model, the
user and the provider, not about the repository.

### 3. The v3 commands live in v3

`edgar stats` and `edgar history show|distill` are in `learning/cli.py`, not
beside the other inspection commands under `cli/`. This is forced, not preferred:
`tests/unit/test_architecture.py` builds a static import graph that sees imports
inside function bodies, so a lazy `import edgar.learning` in a `cli/` module
fails it exactly like a top-level one. `cli/main.py` dispatches by name with
`importlib`, the same way `cli/setup.py` reaches `attach()`. Deleting the package
removes the commands and nothing else, which is what NFR-12 asks for.

### 4. `history distill` produces pending facts, always

`history.md` contains a `- said:` line, which is model-written text, so the file
is not a safe source. `distill()` saves with provenance `"distilled"`, which is
deliberately *not* in `memory/store.py`'s `ACTIVE_FROM`. The store therefore puts
every one of them in `pending` by construction — `distill()` has no code path to
an active fact, not even a wrong one. `edgar memory review` is the only way they
become active.

### OQ-1: `history.md` is gitignored by default

Resolved as the PRD leaned: gitignored, with a documented opt-in.
`.edgar/history.md`, `.edgar/history.1.md` and `.edgar/learning.db` are in
`templates/gitignore.fragment`, so `edgar init` ignores them. The reasoning: a
history file is one person's sessions, not the project's shared state, and the
cost of a mistake is asymmetric — an unwanted commit of a redacted-but-personal
log is worse than having to add one line to commit it on purpose.

## What was cut, and why

**MEM-14's out-of-band model call to condense a long prompt is not built.**
`condense()` keeps the first 40 words and says how many it dropped. Two reasons:
a page whose value is that a human can read it does not need a language model to
produce it, and a project whose positioning is "no hidden calls" should be slow
to add one to a background writer that runs after every turn. Nothing is lost —
the verbatim prompt is in `learning.db`, so a later milestone can add the call
over the same data if it earns its keep.

Per the roadmap's rule this is a cut from the end of the list, recorded rather
than quietly skipped.

## Consequences

- `just loc` reads **9,766 / 12,000** for the v3 tier, and **9,359 / 9,500** for
  `src/` without the removable packages. The second number is the binding one:
  141 lines of code outside `learning/`, `controller/`, `schedule/`, `broker/`
  and `providers/escalation.py` for all of M13, M14 and M15. Anything those
  milestones need in Core, v1 or v2 has to be paid for by simplifying something
  that is already there.
- `ToolFinished` gained a field. It is keyword-only with a default, so no
  existing emit site or subscriber changed, but event fields are part of the 1.0
  format freeze (EXT-10) and this is an addition to that surface.
- One gap found while wiring it: `tools/execute.py`'s `_failed()` path returns
  before emitting `ToolFinished` at all, so validation, permission-denied and
  unknown-tool failures never reach the bus and cannot be learned from. That is
  pre-existing and out of M12's scope; it is written down here so M13 can decide
  whether those failures should be on the bus.
- A subagent's failures still count toward `REPEATS`: they happen in the same
  project and the record has the same shape whoever ran the tool. Only its
  *prompts* are excluded.

## Alternatives considered

- **Filter the fact text instead of the event type.** ADR-0017's option A.
  Rejected there; nothing in building it changed the argument.
- **Put `stats` and `history` in `cli/inspect.py` with a lazy import.** Fails the
  import-graph test, which is right: a lazy import is still an import.
- **Let `distill()` mark high-confidence proposals active.** This is the
  attractive mistake. Confidence is not provenance: a very repetitive pattern
  extracted from model-written text is still extracted from model-written text.
