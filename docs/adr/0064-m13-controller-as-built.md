# ADR-0064: M13, the controller, as built

- Status: accepted
- Date: 2026-09-18
- Implements the M13 row of [`docs/ROADMAP.md`](../ROADMAP.md). Supersedes
  [ADR-0008](0008-controller-guardrails.md) on two points, named in §7 and §8.
  Follows [ADR-0063](0063-m12-learning-foundations-as-built.md) in v3.

## Context

M13 is the feature everybody wants and nobody can make safe: an agent that
adjusts its own settings. The reason it is hard is not subtle. The component
deciding what to change is a language model; the thing it is changing is the
sandbox that model runs in; and the text it reasons over came out of a session
that may already have gone wrong. Give it a free hand and you have built a
machine that argues itself out of its own restraints.

ADR-0008 set the guardrails three years of this design have been built around:
deterministic triggers, a hard-limited tool set, a schema-validated whitelist,
dry-run by default, tighten-only, never fail the turn, a separately configured
model. This ADR records how they were actually implemented, the four decisions
the roadmap asked to be written down, and the two places the implementation went
somewhere ADR-0008 did not.

## Decision

### 1. The controller's model call passes no tools at all

ADR-0008 says "hard-limited tool set". The limit that needs no maintenance is
zero. `gate.py` calls `provider.stream(prompt, [], …)`: the controller cannot
read a file, run a command, search, or call anything whatsoever. Its entire power
is the *shape of its answer*, and that answer is one of eight types.

This is worth stating as a decision rather than an implementation detail, because
"limited" is a moving target. A list of two safe tools becomes three; the third
one turns out to read the filesystem. A list of zero has no next entry. Anything
the controller needs to know has to arrive in the outline it is given, which is
also where the review effort belongs.

`tests/unit/test_controller_gate.py` asserts the provider saw an empty tool list,
not just that the controller behaved.

### 2. Arithmetic decides whether a model is called

`triggers.py` is five comparisons over five numbers, pure in the same way
`permissions.decide()` and `routing.select_model()` are: the caller does the I/O
and hands the results in. If no threshold trips, no request goes out, and an
ordinary turn costs nothing at all — no call, no latency, no token.

The alternative, asking a cheap model whether a call is needed, makes every turn
pay for a request whose usual answer is "no", which is precisely the hidden cost
this project's positioning says it does not have. `[controller] mode = "always"`
is there for people who want the per-turn look and know what it costs.

`[controller] enabled` defaults to **false**. A harness whose promise is "no
hidden calls" does not start making one a turn because you upgraded.

### 3. The whitelist is a tagged union, and there is no `learn`

`proposals.py` parses one JSON object into one of eight frozen dataclasses or
into a `Rejected` saying why not. The shape deliberately mirrors
`permissions/policy.py`'s `Allow | Deny | Ask`: a union is a whitelist the type
checker enforces, which is a better place for one than a prompt.

ADR-0008 listed seven shapes and one of them was `learn`. ADR-0017 removed it: an
active fact may come only from text a human typed or an `ErrorRecord` the harness
computed, and a controller's summary of a session is neither. The eight are
`compact`, `switch_model`, `tighten_policy`, `warn_user`, `abort`,
`propose_instruction`, `propose_skill` and `noop`. A test asserts the eight cases
in the test table *are* `ACTIONS`, so a ninth action cannot be added without a
fabricated proposal exercising it, and `{"action": "learn"}` has its own test
showing it is refused and logged.

### 4. `abort` narrows the live policy to read-only

**A decision the roadmap asked to be recorded.** The gate runs *after* a turn, so
by the time `abort` is parsed there is no turn left to abort. Three options: make
it a no-op with a warning, wire a cancellation path back into the loop, or give
it a different meaning.

It got a different meaning: `narrow()` to `read-only` for the rest of the
session, in memory, never persisted. Not a consolation prize. The failure `abort`
exists for — a model looping, repeating the same edit, burning budget — continues
into the *next* turn, and read-only is exactly what stops it. Wiring cancellation
back into `core/loop.py` was rejected on two grounds: the loop is at its 200-line
cap with zero headroom, and a v3 package that can cancel Core's turn is a much
larger seam than one that can only make a policy stricter.

The session ends with the process, so there is nothing to revert beyond starting
a new one.

### 5. `switch_model` and `compact` persist as derived overrides, dry-run by default

**A decision the roadmap asked to be recorded**, twice: how each one persists.

Both are written to the mutation log in `.edgar/controller.db` with `state =
"proposed"`, which changes nothing. `edgar controller apply ID` sets the row to
`applied`. At the next session start, `cli/setup.py`'s `runtime()` calls
`overrides(root)` through the same `importlib` seam that reaches `attach()`, and:

- `switch_model` becomes a `Selection(model, "controller", …)`, which `--model`
  and `/model` still outrank;
- `compact` becomes `replace(config.context, compact_at=…)`.

Neither writes `config.toml`. Neither adds a line to `core/loop.py`, which does
not know the controller exists.

There is deliberately **no table of current settings**. What edgar is running
under is derived by one query: the newest `applied` row per action. So reverting
is a single `UPDATE` on a single row, and the audit log and the live state cannot
disagree — the shape `memory/store.py`'s undo reached from the other direction.

`tighten_policy` is the exception to dry-run, and that is the third decision a
reasonable person could make differently. CTRL-8 already guarantees the change
can only make the session stricter, and a tightening that waits for a human to
approve it is a tightening that does not happen while the thing it reacted to is
still going on. It is logged like everything else and dies with the session.

### 6. Tighten-only is a pure function with a self-check, property-tested

`narrow(policy, want) -> Policy | str` is the only judge of a policy change.
`MODES` is ordered loosest-first, so "is this mode looser" is an index
comparison; `shell_deny` and a rule map may only grow, and `write_paths` may only
become a subset. The last step of `narrow()` re-asks `is_narrowing(new, old)` on
its own output and refuses if it somehow widened anything, which is cheap and
catches the class of bug where a future field is added to `Narrowing` and nobody
updates the comparison.

`tests/property/test_controller_tightening.py` generates policies and narrowings
and asserts six properties, of which two are the ones that matter: the answer is
always a narrowing or a refusal, and an accepted narrowing was actually applied.
The second exists because "refuse everything" passes the first.

Writing the tests found two real bugs, both of shape "the parser let it through
and left the refusal to apply time": `{"rules": {"shell": "allow"}}` parsed, and
`{"mode": "god-mode"}` parsed. Both are now refused in the builder, because
whether they are legal does not depend on the current policy. `narrow()` checks
again anyway, for a `Narrowing` built in code rather than read from a proposal.

### 7. `propose_instruction` writes Markdown and never names the target file

**The fourth decision the roadmap asked about, and the first deviation from
ADR-0008**, which specifies "a unified diff against `AGENTS.md` … written to
`.edgar/proposals/<id>.diff`".

Both halves changed. It writes a Markdown note to
`.edgar/proposals/<id>-<slug>.md`, and — the part that matters — the code never
spells the instructions file's name at all. A diff has to name a target, and the
moment a path is in the source it is one careless `write_text` from being opened.
edgar also genuinely does not know which file yours is: `AGENTS.md`, a
`CLAUDE.md`, a prompt profile, several of them. A path this code never spells is a
path it can never open.

`approve()` on a `propose_*` row does not apply it; it prints where the file is
and says it is for you to apply by hand. There is no mode in which edgar edits
the instructions file, so "dry run" is not a meaningful distinction for these two
actions and they are never "applied" in any mode.

Enforced twice, and the roadmap asked which: `tests/unit/test_controller_boundary.py`
does both, so the answer is "both, and here is why". It walks the import graph
from every controller module and asserts none of them can reach
`edgar.memory.store`, `.recall` or `.markdown` — the three that read or write a
fact — which is an architecture test. And it reads every string literal in the
package out of its syntax tree and asserts none is `AGENTS.md`, `CLAUDE.md` or
`config.toml`, which is the grep-style assertion done properly. The import-graph
half is the real guarantee; the literal half catches the specific mistake this
milestone is most likely to make.

`edgar.memory.redact` *is* reachable, through `storage/transcript.py`. It is a
pure secret scrubber that writes nothing, and the test says so in a comment
rather than pretending the package is unreachable.

### 8. `switch_model` is constrained to what the project already names

ROUTE-8 allows the escalation chain or the routing targets. The escalation chain
is M15's and does not exist, so `targets()` is exactly the models this project
already names: every `[[route]]` rule's model plus each role's `[model]` binding.
A string outside that set is refused by the parser and logged. This is what keeps
a controller from routing your prompts to a host you never configured [PRV-15],
and it is marked interim: M15 adds the chain to the same function.

### 9. Never fails the turn, and the shape that guarantees it

`_look()` holds the package's only bare `except`. Around it: the model call is a
background task (`asyncio.ensure_future` plus a module-level set holding it, the
pattern `extensions/hooks.py` already uses for a fired hook), so `_ended()`
returns immediately and nothing after it can reach the turn that just finished.
Every failure — a host that is down, a timeout, nonsense JSON, a refused
narrowing — becomes a row in the `rejected` table.

One consequence is deliberate and worth naming: a `-p` run that exits at once may
cancel a controller call still in flight. That is CTRL-11 working as written. The
turn does not wait for the controller, in either direction.

## What was cut, and why

Nothing in the M13 row was dropped. Four things were bounded rather than built,
each of which M14 or M15 picks up:

- **`propose_skill` writes a proposal file and stops.** There is no
  `skills.synthesis` setting in `config/schema.py` to honour yet, so in M13 the
  action always produces a file under `.edgar/proposals/` and never a skill.
  M14 owns `off | propose | auto` and `learned/` [SKL-10, SKL-11].
- **`learning/synthesis.py` is not built and was not to be** — the task said so.
  The gate is where M14 will hang its trigger; nothing in M13 pre-empts it.
- **The escalation chain half of ROUTE-8**, as above: M15's.
- **No `edgar controller run`.** You cannot request a controller call from
  outside. The gate is the only thing that starts one and a crossed threshold is
  the only thing that asks the gate. A manual trigger would be one line and would
  quietly undo the argument the rest of the package makes.

## Consequences

- `just loc` reads **10,558 / 12,000** for the v3 tier and **9,406 / 9,500** for
  `src/` without the removable packages. M13 spent **47 lines of code** of the
  141 that existed outside v3's folders: `ControllerSection` (11), the two
  `importlib` seams and the two override reads in `cli/setup.py` (26),
  `ControllerActed` (5), the renderer's notice (4), the dispatch line (1). **94
  remain for all of M14 and M15.** `core/loop.py` is untouched at 200 of 200.
- `core/events.py` gained `ControllerActed`. Event fields are part of the 1.0
  format freeze (EXT-10), so this is an addition to that surface, the same
  caveat M12 recorded for `ToolFinished.error`.
- **M12's open gap is left open, knowingly.** ADR-0063 noted that
  `tools/execute.py`'s `_failed()` returns before emitting `ToolFinished`, so
  validation errors, permission denials and unknown-tool calls never reach the
  bus. The consequence for M13 is exact and should be written down rather than
  discovered: the controller's `error_streak` counts *executed* tool failures
  only. A session failing every call on a permission denial trips nothing. Fixing
  it is a Core change, and Core has 94 lines left; it belongs to whoever has
  budget, with a note that it changes what every existing subscriber sees.
- The controller reads its signals off the bus and the spend store, and does not
  import `edgar.learning` at all. That is not tidiness: the two v3 packages are
  deleted together in CI but could be split later, and a controller that needs
  the learner to count its own error streak would be a controller that cannot.
- `edgar controller` is not in `--help`'s epilog, for the same reason `edgar
  stats` and `edgar history` are not: the tier may not be installed.

## Verification

NFR-12, checked rather than asserted. With `src/edgar/controller/` deleted and
the package's own six test files excluded, the suite is **917 passed, 11 failed**,
and all eleven failures are `test_tour.py` and `test_tour_map.py` complaining that
files the tour names are gone — the expected collateral of deleting documented
code, and the same methodology `test_architecture.py` and M12's verification
used. No functional test failed: config, setup, the CLI, the loop and the
architecture test all pass with v3's controller absent. The package was then
restored and `git status --short` was clean.

The other three "done when" criteria: all eight actions are exercised with
fabricated proposals in `tests/unit/test_controller_apply.py`; a loosening and an
arbitrary model are each rejected *and logged*, in both the apply tests and the
gate tests; and no controller path can write `AGENTS.md` or a fact, by the two
tests in §7.

## Alternatives considered

- **A small allowlist of read-only tools for the controller.** Rejected in §1.
  Zero is the only limit that does not drift.
- **A `controller_settings` table holding what is in force.** Rejected in §5: two
  sources of truth about what a system is doing is one more than anyone keeps
  correct.
- **Make `abort` a no-op with a warning.** Honest, and useless. §4.
- **Dry-run `tighten_policy` too, for consistency.** Consistency in the wrong
  direction: it is the one action that cannot hurt you, and delaying it is the
  one delay with a cost.
- **A unified diff against `AGENTS.md`, per ADR-0008.** Rejected in §7. The diff
  is nicer to read and requires the code to know a path it must never open.
- **One commit per roadmap bullet.** Not possible while staying green:
  `test_tour.py` fails the moment a planned stop's files exist, so the tour stop
  and its code must land together. M13 is five commits, each green, grouped the
  way M12's were.
