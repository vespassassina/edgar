# Handoff — start here

For the session picking up M17. Written 2026-09-19, updated 2026-09-23 (twice);
replace it each time work stops, delete it when the list is done. Read it
first, then the three documents under "Read".

## Where things stand

- **M15, escalation and route suggest, is done, committed, not pushed**
  (`f5bbc67` on `feat/m15-escalation-route-suggest`). CI on the prior merge
  commit `475a791` had failed and was already fixed by the very next commit
  `93915e1` (a ULID collision in the image-spill test), which is green on
  `main`.
- **M17, the capability broker, is in progress** on
  `feat/m17-capability-broker`. Not merged, not pushed. Built so far:
  - The pure core: `broker/caveats.py` (`Caveat`, `parse_scope`),
    `broker/ticket.py` (`Ticket`, `attenuate`, `verify_chain`),
    `broker/authorize.py` (`authorize()`) [CAP-2, CAP-5, CAP-9].
  - The `pre_tool` veto stage, wired into the real pipeline: `broker/guard.py`
    (`TicketGuard`, the mutable adapter `tools/execute.py` actually calls),
    a new `Broker` structural Protocol and `ToolContext.broker` field in
    `tools/base.py`, a matching `Runtime.broker` field in `core/loop.py`
    (both `None` by default, so a session with no ticket is unaffected), a new
    `"out_of_scope"` `ErrorKind` in `core/message.py`, and a new
    `ScopeRefused` event in `core/events.py`. `tools/execute.py`'s pipeline is
    now `validate → pre_tool hooks → ticket → permission → run → spill`; the
    ticket check runs on the same resolved `Subject` the permission check
    uses (computed once, via `permissions.matcher.subject()`, reused rather
    than recomputed) [CAP-3, CAP-6].
  - **Return-type gotcha for whoever touches `Broker` next:** the first
    version of `Broker.check()` returned a second Protocol (`ScopeRefusal`,
    matching `authorize.Refusal`'s shape). mypy's Protocol structural
    matching does not follow a *nested* Protocol return type when checking
    whether `TicketGuard` implements `Broker` — it compared `Refusal | None`
    against `ScopeRefusal | None` nominally and failed even though `Refusal`
    has exactly the fields `ScopeRefusal` asks for. Fixed by having
    `Broker.check()` return a plain `tuple[str, str] | None` (caveat, reason)
    instead — a structural type mypy does not need a Protocol to check.
  - **Intent creation**: `broker/intent.py` (`Intent`, `Intents`), the
    subscriber that opens an intent from a typed line, mirroring
    `learning/learner.py`'s "boundary is the subscription" shape. Reads only
    `PromptTyped` at depth 0; ignores `PromptSteered` by design (a correction
    belongs to the run already open, my own extension of that event's own
    reasoning, not an explicit ADR-0039 line — flag it if it matters later)
    [CAP-1]. Still not attached to a real bus — that lands with the receipt
    subscriber, item 5 below.
  - **`--scope KEY=VALUE` and `/scope`**, live end to end: `-p --scope
    paths=a.txt` and the REPL's `/scope paths=a.txt` (bare shows the ticket,
    `/scope clear` resets) both build a real `TicketGuard` and refuse a call
    outside it [CAP-2]. Wiring is centralised in `cli/setup.py`, which is the
    only non-removable file that reaches `edgar.broker` — through two new
    public functions, `broker_guard(scope)` and `broker_describe(guard)`,
    both `import_module`-by-name like `_escalation`/`_controller` (so
    `cli/main.py`, `cli/oneshot.py`, `cli/repl.py` and `cli/slash.py` never
    import `edgar.broker` themselves, only call these two). `begin()` gained
    a `scope: tuple[str, ...] = ()` keyword that applies the guard right
    after the `Runtime` is built. `/scope` reuses the exact same functions,
    swapping `shell.rt` via `dataclasses.replace` the way `/model` already
    does. This pulled forward what "Where things stand" used to call item 7
    (the wiring seam) — doing `--scope` without it would have built a flag
    that does nothing, so the two were built together.
  - Tests: `tests/unit/test_broker_caveats.py` (20), `tests/property/test_broker_chain.py`
    (2 hypothesis tests, CAP-5), `tests/unit/test_broker_guard.py` (6, the
    veto stage exercised through the real `execute()` pipeline with a fake
    tool), `tests/unit/test_broker_intent.py` (6),
    `tests/property/test_broker_intent_boundary.py` (1 hypothesis test,
    modelled on `test_learning_boundary.py`'s `ACTIVE_FROM` check),
    `tests/integration/test_oneshot.py::test_scope_refuses_a_read_outside_it`
    and four `/scope` cases in `tests/integration/test_repl.py`. All pass;
    `just check`'s non-tour suite (1140 tests) is green; `ruff format`,
    `ruff check` and `mypy --strict` are clean project-wide.
  - **`task` attenuates the parent's ticket on delegation**: `TicketGuard.narrowed()`
    in `broker/guard.py` calls `ticket.attenuate()` with the subagent's own
    subject (`task:<agent>#<session id>`), the agent's `tools:` folded in as a
    `tools=` caveat, and any model-given `scope` argument merged in — both only
    ever add caveats [CAP-5]. `tools/base.py`'s `Broker` Protocol gained a
    matching `narrowed()` signature; `agents/spawn.py`'s `spawn()` calls it
    when `ctx.broker` is set and passes the result into the subagent's own
    `Runtime.broker`; `task`'s schema gained an optional `scope` array,
    threaded straight through in `tools/builtin/task.py`. Tests:
    `tests/unit/test_spawn.py` (two new cases through the real pipeline) and
    `tests/unit/test_broker_guard.py` (two direct on `narrowed()`). **The
    controller's `tighten_policy`, ADR-0039's fourth caveat source, is not
    built** — `Narrowing`/`TightenPolicy` only ever touched `permissions.Policy`
    fields, nothing ticket-shaped. It is a separate, larger feature (a new
    `Narrowing` field, `Site` needing broker access, `gate.py` validation) —
    see item 1 below, split out on purpose rather than folded into this one.
  - **Budget is now the binding constraint.** `just loc` reads
    `9480 / 9500` outside the removable packages — **20 lines of code of
    headroom left**, down from 36, because the three non-removable files
    `task`'s delegation touched (`tools/base.py`, `agents/spawn.py`,
    `tools/builtin/task.py`) cost 16 lines of code between them. Everything
    still on the list below that touches a non-removable file (the controller
    item, the `edgar receipt` command, `config/schema.py`'s `[broker]`
    section, the `doctor` line) must fit in what is left — keep the real
    logic inside `broker/`'s own modules and let each call site stay one or
    two lines, the way `broker_guard()`/`broker_describe()` do for `--scope`.
- **v2 is complete in code.** The 2.0 release itself and its two human criteria
  (a two-week dogfood period, an outside person's PRD §11 checks) are still
  open, and the release needs the maintainer's explicit authorisation, as every
  push, tag and release in this project does.

## A bug worth knowing about if you touch `ticket.py` again

The first version of `verify_chain()` compared whole `Caveat` objects with
`set(parent.caveats) <= set(child.caveats)`. That is wrong: `attenuate()`
legitimately *rewrites* a caveat's value string when it widens a list
(`tools=a` + `tools=b` → `tools=a,b`) or narrows `calls`/`until` (min of the
two). A rewritten value is a different object, so the naive set check flags
even an honest attenuation as a forgery. A hypothesis property test caught it
immediately (`test_honest_attenuation_always_verifies`). The fix,
`_at_least_as_strict()`, compares *meaning* per kind: list caveats need the
parent's comma-separated items to be a subset of the child's; `calls` and
`until` need the child's number/instant to be no larger than the parent's.
The lesson for `authorize.py` or anywhere else that reads a caveat's value:
never compare `Caveat` values as opaque strings once more than one kind can
hold a value that legitimately changes shape.

The property test's own generator had a matching bug: it drew arbitrary
strings ("a", "b", "c") for every kind including `calls` and `until`, which
`int()` and `datetime.fromisoformat()` then choked on. Fixed by generating
kind-appropriate values (`calls` → an int string, `until` → a real ISO
instant), since no real caveat reaches a `Ticket` except through
`parse_scope()`, which already validates both.

## What M17 still needs

Everything below is unbuilt. Roadmap order, from
[`ROADMAP.md`](ROADMAP.md) "M17 — Capability broker". Items 1 (the veto
stage), 2 (intent creation), 3 (`--scope`/`/scope`, with the wiring seam
pulled forward into it) and 4 (`task` attenuation on delegation) are now
done — see "Where things stand" above; renumbered from there.

1. **The controller's `tighten_policy` adds caveats to a live ticket**
   (ADR-0039's fourth caveat source, CTRL-8) — split out from the item above
   because it does not exist yet at all, not even partially: `Narrowing` and
   `TightenPolicy` in `controller/proposals.py` only carry `permissions.Policy`
   fields (`mode`, `shell_deny`, `write_paths`, `rules`); `controller/apply.py`'s
   `_tighten_policy()` only ever calls `permissions.narrow()`. This needs a new
   `Narrowing` field for ticket caveats, `Site` (wherever it lives today) to
   reach the broker the way `ToolContext`/`Runtime` do, and `gate.py` to
   validate and apply it — call `ticket.attenuate()` the same way `task` now
   does, not a new merge function. Bigger than the other items on this list;
   budget it as its own pass, not a line or two.
2. **`broker/receipt.py`**: append-only, hash-chained, HMAC-SHA256-signed
   JSONL at `.edgar/sessions/<id>/receipt.jsonl` (`Session.dir` already
   exists structurally). Key at `~/.edgar/receipt.key`, 32 random bytes
   created on first use, added to the hard layer's credential paths so the
   agent's own tools cannot read it. Entry kinds: `intent`, `ticket`,
   `delegate`, `allow`/`refuse`, `permission`. Nothing here exists yet —
   wholly new code, no hash-chain/HMAC precedent anywhere else in the repo.
   Attaching its event-bus subscriber (and `Intents`, still unattached) is
   one more small addition to `cli/setup.py`'s `begin()`, next to where
   `scope=` already applies the guard.
3. **`edgar receipt [ID] [--refused] [--verify]`** CLI command; `--verify`
   checks the chain/signatures and exits 1 at the first break.
4. **`[broker] enabled` config section** (`config/schema.py`), default
   `True`, plus an `edgar doctor` report line.
5. **Bump `tests/support/budget.py`'s `TARGET_TIER`** from `"v3"` to
   `"v4"`. Not done yet — `just check` currently fails on the tour tests
   below, not on budget, but do this before the tour work so `just loc`
   reports against the right ceiling.
6. **The confused-deputy integration test** named in the roadmap's "Done
   when": a session scoped `paths=reports/q3.md`, injected content tries to
   read `reports/2024-salaries.md` and fetch an outside host, both refused,
   `edgar receipt --refused` shows both, `--verify` catches a one-byte
   tamper.
7. **Tour delivery**: `docs/tour/broker.html`, turn stop `s29` (per the
    roadmap row — check it against `docs/tour/index.html` directly, the way
    M14's handoff caught a stale id) into a link, then `just map`.

Only **20 lines of code of headroom** remain outside the removable
packages (see "Where things stand" above) — items 2–4 each touch a
non-removable file and must be kept to a line or two each, real logic
inside `broker/receipt.py` and the admin command's own removable-tier
module. Item 1 (the controller) is the exception: it is genuinely bigger
than what is left, so it may need its own budget conversation with the
maintainer rather than a squeeze.

`just check` currently fails with five tour/map test failures
(`test_tour.py`, `test_tour_map.py`) because `broker/caveats.py`,
`broker/guard.py` and `broker/intent.py` exist with no tour stop and the
committed `map.json`/`map.data.js` are stale against the new LOC count.
That is expected and will clear once item 7 above is done — do not try to
make the tour tests pass before the rest of the module is built; the tour
describes what shipped, not what is half-built.

## Read, in this order

1. [ADR-0039](adr/0039-capability-broker.md): the accepted design — Intent,
   Ticket, the five caveats, Option C (checked in the tool pipeline, not
   bound handles or a policy language), the receipt shape.
2. [`ROADMAP.md`](ROADMAP.md), section "M17 — Capability broker" (quoted
   above). Every item names its files, requirement IDs, and the confused-deputy
   acceptance test.
3. [`AGENTS.md`](../AGENTS.md): the standing rules. Lines mean lines of code;
   pseudocode comments in every file you touch; shallow functions; the tour
   changes in the same commit as the code; `just check` before every commit;
   journal, changelog, roadmap status and an ADR when a decision could go
   another way.

## Resume commands

M17 is committed so far only in working tree, not yet committed on
`feat/m17-capability-broker`. From that branch:

```bash
uv run pytest tests/property/test_broker_chain.py tests/unit/test_broker_caveats.py -q
```

```bash
just check
```

```bash
just loc
```
