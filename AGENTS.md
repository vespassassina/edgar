# AGENTS.md

Instructions for AI agents working in this repository. Hand-authored. **No
automated process may modify this file**, including edgar's own controller
(ADR-0007, ADR-0008).

---

## What this project is

edgar is a small agentic harness for the terminal. It is a **teaching artifact
first and a usable tool second**. Where those conflict, teaching wins.

Read before writing code:

1. [`docs/PRD.md`](docs/PRD.md) — requirements, numbered for traceability
2. [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) — architecture, module map, interfaces
3. [`docs/adr/`](docs/adr/) — why things are the way they are
4. [`docs/ROADMAP.md`](docs/ROADMAP.md) — what to build, in order
5. [`docs/TESTING.md`](docs/TESTING.md) — how to test it

[`docs/BRAINSTORM.md`](docs/BRAINSTORM.md) has the original design conversation if
you need the reasoning behind a decision that the ADRs do not cover.

## Non-negotiable constraints

Violating any of these is a bug regardless of whether tests pass.

1. **Startup budget.** `import edgar.cli.main` must not pull in `httpx`, `rich`,
   `prompt_toolkit`, `pydantic` or any `edgar.providers.*` module. Lazy-import
   everything heavy. There is a CI test. [ADR-0012]
2. **Compaction pairing invariant.** No `tool_use` may ever be separated from its
   `tool_result`. Every provider returns 400 if you break it. [CTX-4]
3. **Policy may only tighten.** Nothing at runtime may widen permissions.
   Subagents narrow. The controller narrows. Nothing widens. [PERM-8, CTRL-8]
4. **Machine writers never touch hand-authored files.** `AGENTS.md` and
   `config.toml` are human territory. The controller proposes a diff to
   `.edgar/proposals/`; a human applies it. This file is part of what constrains
   the controller, so a controller that could edit it would be editing its own
   constraints. [MEM-2, CFG-7, CTRL-12]
5. **Escalation goes up, fallback goes sideways, routing decides up front.** Three
   mechanisms, three triggers, never merged into one `pick_model()`. Escalation is
   capped and announced. Fallback never reduces capabilities. [ADR-0013]
6. **Autolearn sources are exactly three:** user prompts, user feedback, errors.
   Never tool output, never fetched web content. This is a security boundary, not
   a preference. [MEM-8, MEM-9]
7. **stdout is the result, stderr is everything else.** No ANSI on stdout when it
   is not a TTY. [CLI-5, CLI-6]
8. **Tool failures return to the model, they do not raise.** The model recovers
   from bad arguments and denials. Only unrecoverable loop failures raise. [§17]
9. **No platform skips in core tests.** If it cannot run on Windows, the code is
   wrong, not the test. [NFR-6]

## Code conventions

**Style.** `ruff format` and `ruff check`. Line length 100. `mypy --strict` clean.

**Types.** Annotate everything public. `from __future__ import annotations` at the
top of every module. Prefer `Protocol` over ABC for interfaces.

**Dataclasses.** `frozen=True, slots=True` for value types. Message and content
blocks are immutable by design, which is what makes compaction naturally
idempotent.

**Async.** The loop, providers and tools are `async`. No threads in core. No
`multiprocessing` (no `fork` on Windows).

**Errors.** Subclass `EdgarError`, set `exit_code`, and always provide a `hint`.
A learning tool that prints `error: 401` has failed at its job.

**Comments.** Only where the code cannot explain itself: a non-obvious invariant, a
provider quirk, a subtle ordering requirement. No comments restating the code. No
docstrings on obvious functions. Where a comment explains *why*, keep it forever.

**Imports.** Standard library, then third party, then local. Heavy imports go
inside functions with a comment naming the reason.

## Architecture rules

**One obvious home per concept.** Compaction lives in `context/compact.py`.
Permission decisions live in `permissions/policy.py`. If you find yourself adding
permission logic to a tool, stop.

**Pure functions where possible.** `decide()`, `compute_due()`, `select_model()`,
`compact()` and token counting are pure by design so they can be tested
exhaustively. Keep them that way. If you need I/O, pass the result in, do not
reach out.

**The event bus is the only output path.** The loop never prints. Tools never
print. They emit events; subscribers render. [ADR-0011]

**A subagent is the same loop.** `task` re-enters `core/loop.py` with a different
config. Do not build a second execution engine. [ADR-0006]

**Providers translate, they do not decide.** Nothing outside `providers/` sees a
provider-native structure. Differences are data in `quirks.py`, not branches in the
loop.

## Size discipline

| Target | Limit |
|---|---|
| `core/` | ≤ 2,000 LOC |
| `src/` total | ≤ 8,000 LOC at v1.0 |
| `core/loop.py` | ≤ 200 lines |
| Direct dependencies | ≤ 8 |

If a file is growing past ~300 lines, it is probably doing two things. These
numbers exist because a harness you cannot read teaches nothing.

## Testing

Full detail in [`docs/TESTING.md`](docs/TESTING.md). The rules that matter while
writing code:

- **Use the fake provider** unless the test specifically exercises provider
  translation. No network in the offline suite; `no_network` is applied suite-wide
  and will fail loudly.
- **New provider?** It is done when the contract suite passes for it, not when it
  works once by hand.
- **New pure function?** Property-test it.
- **Touching compaction, permissions, routing or paths?** Add a property test.
  These four are where correctness actually lives.
- **Asserting loop behaviour?** Assert on the event sequence. It is usually the
  clearest expression of intent.

```bash
just check      # ruff + mypy --strict + offline tests. Run before every commit.
just test       # offline suite
just cov        # coverage report
```

## Working on a milestone

1. Read the milestone in `ROADMAP.md` and the requirement IDs it names
2. Read the relevant BLUEPRINT section and any referenced ADR
3. Write the tests first where the shape is clear from the requirement
4. Implement
5. `just check`
6. Update docs in the same commit, never "later"
7. If you made a decision a reasonable person would make differently, write an ADR

## When you disagree with the spec

Say so. The spec is a design, not scripture, and several decisions in it were close
calls documented with their rejected alternatives.

**Do not silently deviate.** If BLUEPRINT says one thing and you build another, the
docs become untrustworthy and the teaching value collapses. Raise it, decide, then
update the doc and the code together.

## Commits

Conventional commits. Reference requirement IDs where relevant.

```
feat(providers): add anthropic adapter [PRV-2]
fix(context): widen cut point when tool pair spans boundary [CTX-4]
docs(adr): record session storage decision, resolves OQ-5
test(permissions): property test hostile path inputs [PERM-5]
```

Keep commits focused. A commit that touches the loop, a provider and the docs for
three unrelated reasons is a commit nobody can review.

## What not to do

- Do not add a dependency without justifying its import cost in the PR
- Do not add a config knob because it might be useful. Knobs are permanent.
- Do not build anything in the "Never" list in `ROADMAP.md`
- Do not create planning or tracking markdown files in the repo
- Do not weaken a test to make it pass
- Do not add a `# type: ignore` without a comment naming the reason
- Do not silently degrade behaviour. Fail loudly with a hint.
