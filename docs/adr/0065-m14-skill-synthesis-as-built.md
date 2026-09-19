# ADR-0065: M14, skill synthesis, as built

- Status: accepted
- Date: 2026-09-19
- Implements the M14 row of [`docs/ROADMAP.md`](../ROADMAP.md). Inherits the
  boundary of [ADR-0017](0017-learning-boundary.md) and the gate of
  [ADR-0064](0064-m13-controller-as-built.md). Resolves **OQ-6**.

## Context

A skill is not a note. It is a file whose one-line description enters the prompt
of every future session, and whose body the model may open and follow. Writing
one automatically means letting a run that read files, ran commands and fetched
pages decide what the agent is told to do next month.

ADR-0017 already closed four roads by which text the harness did not choose could
become an active fact. Skill synthesis is a fifth road and the widest of them:
its output is not a fact the model may read, it is an instruction the model is
handed. So M14 is arranged less around writing skills well and more around the
list of things the writer may not read and the places it may not write.

## Decision

### 1. `Turn` has seven fields and no eighth, and that is the filter

`learning/synthesis.py`'s `Turn` can hold the typed prompt, typed corrections,
tool **names** in call order, `ErrorRecord`s, the verification result, the agent
name and the skills already loaded. There is no field for a tool's output, an
error message or a fetched page. `Outline.render()` cannot leak what `Turn`
cannot hold.

The alternative is a filter: take the whole run, strip what looks like tool
output. Filters lose, because there is always one more shape the filter did not
know about, and a filter that falls behind fails silently. A type cannot fall
behind. Adding a field to `Turn` is therefore this ADR being superseded, not a
patch.

### 2. Tool arguments are excluded, though SKL-9 allows them

SKL-9 lists tool arguments among what the synthesiser may see. They are left
out. An argument is text the model composed *after* reading the previous tool's
result, so "put the contents of the file you just read into the next command" is
a working laundering path from tool output into a standing instruction. Tool
names come from a closed set; arguments come from anywhere.

The cost is real — a skill that cannot name the flag that worked is a weaker
skill — and it is accepted. A reasonable person could take the other side here,
which is why it is a numbered decision rather than a comment.

### 3. `_error()` re-sanitises a field the pipeline already sanitised

`ErrorRecord.program` is a basename the model chose. The tool pipeline strips it
to `[A-Za-z0-9._-]` before recording it. `_error()` strips it again. Duplication
is normally the thing to refuse; here it is one line, and it survives the day one
of the two paths changes. The property test found this: before it was added,
generated shell metacharacters in `program` reached the synthesiser's prompt
verbatim.

The regex is **spelled again** rather than imported from
`learning/error_facts.py`, because that module reaches `memory/store.py` and
`tests/unit/test_controller_boundary.py` forbids any controller module from
reaching the code that writes a fact. The static import graph catches
function-level imports, so a guarded import would not have helped.

### 4. OQ-6 is resolved: a task shape is `agent:tool>tool`

`shape_of(agent, tools)` in `learning/experience.py` returns the agent name (empty
for the main loop), a colon, and the deduplicated tool names in first-call order,
joined by `>`: `main:shell>edit`. It lives in `experience.py` rather than
`synthesis.py` because the experience store counts shapes and importing the other
way round would be circular.

Rejected: hashing the prompt (two phrasings of the same job never match), and
counting tools without order (`edit>shell` and `shell>edit` are different jobs —
one edits then tests, the other tests then edits). Order without repetition is
the coarsest thing that still tells those apart.

### 5. Observations live in one machine-owned folder, not per-skill `HISTORY.md`

SKL-14 says "that skill's `HISTORY.md`". Taken literally, edgar would write a
file inside a folder a person authored. It does not. Every observation goes to
`.edgar/skills/learned/.history/<name>.md`, one file per skill name, whatever the
skill's origin.

A hand-authored skill is still observed and still gets patches proposed — the
feature survives intact. What changes is the invariant that **nothing edgar
writes ever lands beside a file you wrote**, which is the same rule
`write_learned()` enforces for the skill itself. PRD §9.5's machine-writable list
gains one folder rather than every skill folder on the disk.

### 6. `archive()` and `LEARNED` live in `skills/discovery.py`

`edgar skills forget` has to work with the whole learning package deleted
(NFR-12), and `cli/admin.py` is v2, which may not import v3 even inside a
function. So the move-to-`.archive` helper and the `learned/` path constant sit
in the non-removable `skills/discovery.py`, next to `BODY_SECTIONS` and
`body_shape()`, which `skills validate` needs for the same reason. One definition
also means the writer and the checker cannot disagree about what a learned skill
looks like.

`forget` archives rather than deletes: a machine wrote the file and a person may
still want to read what it thought.

### 7. `skills distill` depends on the controller instead of duplicating its rule

`edgar skills distill NAME` makes a model call, and `cli/admin.py` documents that
none of its subcommands contacts a model. So the command is
`learning/distill.py`, dispatched by name through `importlib`, and it routes its
answer back through the controller's `parse()` and `apply()`.

Writing the file directly would have been shorter and would have removed a
dependency between two removable packages. It was refused: "propose or write, and
under which conditions" is one decision, it lives in `controller/apply.py`, and a
second copy is a second copy that drifts looser. A project with the controller
deleted gets a sentence saying so.

### 8. `[skills]` is flat, and has no `curator` keys at all

PRD §5 spells some of these nested (`synthesis_triggers.min_tool_calls`,
`curator.enabled`). A config section here is a flat table of scalars — a nested
table would be read as a value of the wrong type — so the names are kept and the
nesting dropped.

There are no `curator` keys, because **SKL-15 (`learning/curator.py` and `edgar
skills curate`) is cut**. It is a *Should*, and the non-removable line budget had
nothing left (§10). A config key that parses cleanly and then does nothing is
exactly the hidden behaviour this harness promises not to have, so the two keys
that had been added speculatively were removed again.

### 9. The `auto` disclaimer prints only when the controller package is present

SKL-13's disclaimer is printed once per session from `cli/setup.py`, inside
`_controller()`, after `import_module("edgar.controller")` has succeeded. A
project with v3 deleted therefore sees nothing — which is correct, because with
the gate gone nothing can be written, and a warning about a risk that cannot
occur trains people to ignore warnings. It is recorded here because it is a
deviation a reader might otherwise take for a bug.

The `correction` trigger can only ever *propose*, even in `auto`. It is the one
trigger that does not require a passing check, and pairing it with an unreviewed
write would be the single hole in "verified or nothing".

### 10. The binding constraint was the non-removable budget, not the tier budget

v3's tier budget is 12,000 lines of code and `src/` reads 11,073. The number that
actually constrained M14 is `src/` **without** the removable packages: 9,495 of
9,500, five lines for the whole of M15.

Everything that could go in `learning/` or `controller/` did. What had to be
non-removable — `skills/discovery.py`'s shape and archive helpers, `skills list
--learned`, `skills forget`, the validate branch, the doctor line, the `auto`
disclaimer — was compressed until it fit, and SKL-15 was cut.

**M15 cannot be built against five lines.** Per the standing rule, the budget does
not move: something in v3 has to become removable, or M15's non-removable surface
(`edgar route suggest` is the obvious one) moves to a later tier. That decision
belongs to whoever plans M15 and should be made before any code is written.

## Consequences

- The synthesiser reads names, counts and typed text. It will sometimes write a
  vaguer skill than a human would. That is the trade.
- `propose` is the default and `auto` announces itself every session.
- `tests/property/test_synthesis_boundary.py` generates both the trajectory and
  the synthesiser's answer, and asserts in `auto` mode that every file a person
  wrote is byte-identical afterwards. It is the test to run when any of this
  changes.
- SKL-15 is unbuilt and unconfigured. Whoever picks it up starts from `archive()`
  in `skills/discovery.py`, which already does the only dangerous part.
