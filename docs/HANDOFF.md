# Handoff — start here

For the session picking up M17. Written 2026-09-19, updated 2026-09-23;
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
  `broker/caveats.py` (`Caveat`, `parse_scope`), `broker/ticket.py` (`Ticket`,
  `attenuate`, `verify_chain`), `broker/authorize.py` (the pure `authorize()`
  check) [CAP-2, CAP-5, CAP-9], with `tests/unit/test_broker_caveats.py` (20
  tests) and `tests/property/test_broker_chain.py` (2 hypothesis tests, CAP-5).
  All pass; `ruff format`, `ruff check` and `mypy --strict` are clean on all
  five files. **Nothing outside `src/edgar/broker/` has been touched yet** —
  the module is not wired into the tool pipeline, so it currently does
  nothing at runtime.
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
[`ROADMAP.md`](ROADMAP.md) "M17 — Capability broker":

1. **The `pre_tool` veto stage does not exist yet in the shape ADR-0039
   describes.** What exists today (`extensions/hooks.py`'s `veto()`, called
   from `tools/execute.py`) is the M10 subprocess-based `[[hooks]]` mechanism
   — a different thing. M17 needs a new in-process, Python-callable veto
   check in the tool pipeline: read `subject()` from
   `permissions/matcher.py` (already resolves a call's path/command/URL into
   a `Subject` — reuse it, do not reimplement), call `broker.authorize.authorize()`
   with the session's live `Ticket`, and on refusal return
   `_failed(call, "out_of_scope", ...)`. `"out_of_scope"` is a new
   `ErrorKind` value in `core/message.py`. `ToolContext` in `tools/base.py`
   needs a field to carry the ticket (a `Protocol`-typed field on `Runtime`
   too, mirroring `Runtime.escalation`, so `core/loop.py` never imports
   `edgar.broker`).
2. **Intent creation**, restricted to the same call sites that emit
   `PromptTyped`/`PromptSteered` (`cli/repl.py`'s `submit()`,
   `cli/oneshot.py`'s `run_prompt()`) — never from tool output, fetched
   content, or model text, mirroring the MEM-8 boundary. Needs its own
   property test analogous to `store.py`'s `ACTIVE_FROM` allowlist test.
3. **`--scope KEY=VALUE`** (repeatable) on `-p` (`cli/main.py`), and
   **`/scope`** in the REPL (`cli/slash.py` — bare shows the current ticket,
   `/scope clear` resets). Both build on `caveats.parse_scope()`, already
   built.
4. **`task` attenuates the parent's ticket** on delegation; the
   controller's `tighten_policy` adds caveats to a live ticket. Both call
   `ticket.attenuate()`, already built.
5. **`broker/receipt.py`**: append-only, hash-chained, HMAC-SHA256-signed
   JSONL at `.edgar/sessions/<id>/receipt.jsonl` (`Session.dir` already
   exists structurally). Key at `~/.edgar/receipt.key`, 32 random bytes
   created on first use, added to the hard layer's credential paths so the
   agent's own tools cannot read it. Entry kinds: `intent`, `ticket`,
   `delegate`, `allow`/`refuse`, `permission`. Nothing here exists yet —
   wholly new code, no hash-chain/HMAC precedent anywhere else in the repo.
6. **`edgar receipt [ID] [--refused] [--verify]`** CLI command; `--verify`
   checks the chain/signatures and exits 1 at the first break.
7. **`[broker] enabled` config section** (`config/schema.py`), default
   `True`, plus an `edgar doctor` report line.
8. **`cli/setup.py`'s `_broker(...)`** `import_module`-by-name seam,
   mirroring `_escalation`/`_controller`/`_learning` — both an event-bus
   subscriber for the receipt writer and the `Runtime`-carried ticket field.
9. **Bump `tests/support/budget.py`'s `TARGET_TIER`** from `"v3"` to
   `"v4"`. Not done yet — `just check` currently fails on the tour tests
   below, not on budget, but do this before the tour work so `just loc`
   reports against the right ceiling.
10. **The confused-deputy integration test** named in the roadmap's "Done
    when": a session scoped `paths=reports/q3.md`, injected content tries to
    read `reports/2024-salaries.md` and fetch an outside host, both refused,
    `edgar receipt --refused` shows both, `--verify` catches a one-byte
    tamper.
11. **Tour delivery**: `docs/tour/broker.html`, turn stop `s29` (per the
    roadmap row — check it against `docs/tour/index.html` directly, the way
    M14's handoff caught a stale id) into a link, then `just map`.

`just check` currently fails with five tour/map test failures
(`test_tour.py`, `test_tour_map.py`) because `broker/caveats.py` exists with
no tour stop and the committed `map.json`/`map.data.js` are stale against the
new LOC count. That is expected and will clear once item 11 above is done —
do not try to make the tour tests pass before the rest of the module is
built; the tour describes what shipped, not what is half-built.

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
