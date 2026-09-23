# Handoff — start here

For the session picking up M17. Written 2026-09-19, updated 2026-09-23 (three
times); replace it each time work stops, delete it when the list is done. Read
it first, then the three documents under "Read".

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
  - **The receipt**: `broker/receipt.py` (`Receipts`, `append`, `verify`,
    `load_or_create_key`), append-only, hash-chained, HMAC-SHA256-signed
    JSONL at `.edgar/sessions/<id>/receipt.jsonl`, keyed by
    `~/.edgar/receipt.key` (32 random bytes, 0600, made on first use, added
    to `permissions.matcher`'s new `CREDENTIAL_FILES` so the model's own
    tools cannot read it). `Receipts` subscribes to the bus the same way
    `Intents` does: `intent`, `delegate`, `refuse` and `permission` lines
    from events, `ticket` written directly once by `record_ticket()`.
    `broker/__init__.py`'s new `attach()` wires both subscribers;
    `cli/setup.py`'s `begin()` calls it unconditionally through a new
    `_broker()` [ADR-0039, CAP-9].
  - **`edgar receipt [ID] [--refused] [--verify]`**: real logic in the new,
    removable `broker/cli.py`; reached from `cli/main.py` through the same
    by-name dispatch `stats`/`history`/`controller` already use, one dict
    entry added, no new branch.
  - **`[broker] enabled`** (`config/schema.py`, default `true`) and its
    `edgar doctor` line. `false` turns off both the veto and the receipt
    through `_broker()`'s own gate — a setting that read fine and did
    nothing would be exactly the hidden behaviour this harness promises not
    to have.
  - Tests: `tests/unit/test_broker_receipt.py` (11), `tests/unit/test_broker_cli.py`
    (6), `tests/integration/test_broker_setup.py` (2), one new case in
    `tests/unit/test_policy.py`, two in `tests/unit/test_config.py`. All
    green; `just check`'s non-tour suite is 1166 passed (up from 1157).
  - **Budget is now exhausted, not just tight.** `just loc` reads
    `9500 / 9500` outside the removable packages — **zero lines of code of
    headroom left**, down from 20. This pass's five non-removable touches
    (`cli/main.py` 5, `permissions/matcher.py` 4, `config/schema.py` 6,
    `cli/setup.py` 2, `cli/doctor.py` 1) used exactly what remained. **Item 1
    below (the controller) cannot be built without either simplifying
    existing non-removable code first or raising the ceiling — that decision
    is the maintainer's, not a squeeze to attempt.** Item 5 (bumping
    `TARGET_TIER` to `"v4"`) raises the *total*-tier ceiling (12,000 → 13,000)
    but not this one (`TIER_BUDGETS["v2"]`, 9,500, is what "without removable
    packages" checks against at v3 and v4 alike) — it does not create room
    by itself.
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

Items 2 (the receipt), 3 (`edgar receipt`) and 4 (`[broker] enabled`) are now
also done — see "Where things stand" above. Renumbered again from there.

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
   budget it as its own pass, not a line or two. **Blocked on budget: zero
   lines of code of headroom remain outside the removable packages (see
   "Where things stand" above); raise this with the maintainer before
   touching any non-removable file for it.**
2. ~~**Bump `tests/support/budget.py`'s `TARGET_TIER`** from `"v3"` to
   `"v4"`.~~ Done: `just loc` now reports `src/ total (v4 tier) 11533 / 13000`.
   As expected, this only raised the *total*-tier ceiling (12,000 → 13,000);
   the "without removable packages" cap is still `9500 / 9500`, so item 1's
   blocker is unchanged.
3. ~~**The confused-deputy integration test** named in the roadmap's "Done
   when".~~ Done:
   `tests/integration/test_confused_deputy.py`, two tests. A ticket scoped
   `paths=reports/q3.md`; a `read` on `reports/2024-salaries.md` is refused;
   a `shell curl` toward an outside host is refused too — `shell`'s `Subject`
   is neither a path nor a URL, so it falls into `authorize()`'s "unchecked"
   branch and is refused outright under `paths=`, not because of a `hosts=`
   check (a `fetch`-style URL-shaped call would need `hosts=` to be refused;
   `paths=` alone does not constrain it — worth remembering if this test is
   ever extended to a real network-fetch tool). Both refusals verified in the
   signed receipt chain, then exercised through `edgar receipt --refused`
   and `--verify`, including a one-byte tamper turning `--verify`'s exit
   code from 0 to 1. Pure test code, no non-removable touch; `just loc` is
   unchanged at `9500 / 9500`.
4. ~~**Tour delivery**: `docs/tour/broker.html`, turn stop `s29` (per the
   roadmap row — check it against `docs/tour/index.html` directly, the way
   M14's handoff caught a stale id) into a link, then `just map`.~~ Done, but
   not quite as first written: the real stop was `s35`, not `s29` (`s29` is
   "Extensions, hooks, plugins, embedding"), and `broker/` at 365 LOC across
   7 files was closer to the dedicated-page precedent (`extensions.html`,
   `memory.html`) than to the single-file-exception one ADR-0066 §8 records
   for `providers/escalation.py` — ROADMAP.md's own M17 section names
   `docs/tour/broker.html` by name, so that is what got built: four stops
   (intent and the ticket, the veto, the receipt, `edgar receipt` and the
   wiring), a Sizes table, and a nav entry added to all 12 other pages.
   `index.html`'s `s35` is now a short pointer stop into it. `just map` re-run
   clean; `tests/unit/test_tour.py` and `test_tour_map.py` both green
   (160 passed); `just check` green (1182 passed); `just loc` unchanged at
   `9500 / 9500` (docs never counted against it).

There is **no budget headroom left** outside the removable packages (see
"Where things stand" above). **Only item 1 (the controller's
`tighten_policy`) is left on this list**, and it needs the maintainer's
decision before any further non-removable touch — see item 1 above.

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

M17's work through the tour delivery is committed on
`feat/m17-capability-broker`. Only item 1 (the controller) is left, and it is
blocked on the maintainer's budget decision. From that branch:

```bash
uv run pytest tests/integration/test_confused_deputy.py tests/unit/test_tour.py tests/unit/test_tour_map.py -q
```

```bash
just check
```

```bash
just loc
```
