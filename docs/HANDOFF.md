# Handoff — start here

For the session picking up after M14. Written 2026-09-19; replace it each time
work stops, delete it when the list is done. Read it first, then the three
documents under "Read".

## Where things stand

- **M14, skill synthesis, is done** on `feat/m14-skill-synthesis`, committed and
  not pushed ([ADR-0065](adr/0065-m14-skill-synthesis-as-built.md)). New files:
  `learning/synthesis.py`, `learning/observations.py`, `learning/distill.py`,
  `docs/tour/synthesis.html`. `just check` green at 1,082 tests, ruff and mypy
  clean.
- **v3 order so far:** M12 done 2026-09-17 ([ADR-0063](adr/0063-m12-learning-foundations-as-built.md)),
  M13 done 2026-09-18 ([ADR-0064](adr/0064-m13-controller-as-built.md)), M14
  done 2026-09-19. **M15, escalation and route suggest, is next** — and see the
  blocker below before planning it.
- **v2 is complete in code.** The 2.0 release itself and its two human criteria
  (a two-week dogfood period, an outside person's PRD §11 checks) are still
  open, and the release needs the maintainer's explicit authorisation, as every
  push, tag and release in this project does.

## The blocker M15 has to resolve first

`just loc` reads:

```
src/ total (v3 tier)            11073 / 12000
src/ without removable packages  9495 / 9500
core/loop.py                      200 / 200
```

**Five lines of code outside the removable packages, for all of M15.** The tier
budget is not the constraint; the non-removable line is. M14 already put
everything it could into `learning/` and `controller/` and cut SKL-15 (the
curator) to fit.

M15's roadmap items are mostly removable — `providers/escalation.py` is in the
v3 list in `AGENTS.md` rule 10 — but **`edgar route suggest` is not**, and
neither is whatever the status bar needs to announce an escalation. Before
writing any code: read [ADR-0065 §10](adr/0065-m14-skill-synthesis-as-built.md),
decide whether something in v1/v2 becomes removable or `route suggest` moves to
a later tier, and record that decision in an ADR. Per the standing rule, the
budget does not move.

## Read, in this order

1. [ADR-0065](adr/0065-m14-skill-synthesis-as-built.md), then
   [ADR-0064](adr/0064-m13-controller-as-built.md) and
   [ADR-0063](adr/0063-m12-learning-foundations-as-built.md): how v3 is actually
   built, and the ten decisions M14 flagged.
2. [`ROADMAP.md`](ROADMAP.md), section "M15 — Escalation and route suggest".
   Every item names its files, requirement IDs, test and size.
3. [`AGENTS.md`](../AGENTS.md): the standing rules. Lines mean lines of code;
   pseudocode comments in every file you touch; shallow functions; the tour
   changes in the same commit as the code; `just check` before every commit;
   journal, changelog, roadmap status and an ADR when a decision could go
   another way.

## What M14 leaves for whoever comes next

- **The seam between the two removable packages is function-level imports in
  both directions**, each wrapped in `try/except ModuleNotFoundError`. A v1 or
  v2 module reaching v3 must use `importlib.import_module` by name: the static
  import graph in `tests/unit/test_architecture.py` catches a guarded `from`
  import too. Genuinely shared code goes into a non-removable module — that is
  why `archive()`, `LEARNED` and `BODY_SECTIONS` live in `skills/discovery.py`.
- **`learning/synthesis.py` spells its own `UNSAFE` regex** rather than
  importing it from `error_facts.py`, because that module reaches
  `memory/store.py` and `tests/unit/test_controller_boundary.py` forbids any
  controller module from reaching the code that writes a fact. Do not "tidy"
  that duplication away; the comment above it says so.
- **`Turn` is the security boundary.** Adding a field to it is an ADR. If M15
  wants escalation context in a skill, that is the conversation to have first.
- **The property test is the one to run when any of this changes:**
  `tests/property/test_synthesis_boundary.py` generates both the trajectory and
  the synthesiser's answer and asserts, in `auto` mode, that every file a person
  wrote is byte-identical afterwards.
- **SKL-15 is unbuilt and has no config keys.** Whoever picks it up starts from
  `archive()` in `skills/discovery.py`, which already does the dangerous part.
- **M12's gap is still open.** `tools/execute.py`'s `_failed()` returns before
  emitting `ToolFinished`, so the controller's `error_streak` and the
  synthesiser's error list count *executed* tool failures only: a session failing
  every call on a permission denial trips nothing. Fixing it is a Core change
  that alters what every existing subscriber sees. Whoever takes it should say so
  in an ADR — and it costs non-removable lines, so it collides with the blocker
  above.
- **Check tour stop ids against `docs/tour/index.html`, not the roadmap.** The
  M14 row said `s27`; the stop is `s33` (`s27` is MCP). Fixed on this branch.
  M15's row says `s28`; the escalation stop is `s34`.
- **Four documentation gaps** found during M20 are still open, listed in
  `JOURNAL.md`'s M20 entry: no `edgar tools validate`; an HTTP tool's `{slot}`
  missing from `[input].properties` loads silently; `edgar trust` lists a tool
  file by its first comment line; `EXTENDING.md` never gives the HTTP-tool
  grammar in full.

## Proposed diff to `AGENTS.md` (maintainer applies by hand)

`AGENTS.md` is hand-authored (ADR-0007, ADR-0008). Rule 10 and the size table
still describe the removable tier as "v2". Proposed wording:

```diff
-10. **Tier isolation.** Core and v1 code never imports `edgar.controller`,
-    `edgar.learning`, `edgar.schedule`, `edgar.broker` or
-    `edgar.providers.escalation`. v2 attaches
-    through the post-turn gate and the event bus. [NFR-12, ADR-0015]
+10. **Tier isolation.** Core, v1 and v2 code never imports `edgar.controller`,
+    `edgar.learning`, `edgar.schedule`, `edgar.broker` or
+    `edgar.providers.escalation`. v3 and v4 attach through the post-turn gate
+    and the event bus; v2, the daily driver, extends Core and v1 packages and
+    is not removable. [NFR-12, ADR-0015, ADR-0057]
```

```diff
-| `src/` total | Core ≤ 5,000 · v1.0 ≤ 8,000 · v2.0 ≤ 11,000 LOC |
+| `src/` total | Core ≤ 5,000 · v1.0 ≤ 8,000 · v2.0 ≤ 9,500 · v3.0 ≤ 12,000 · v4.0 ≤ 13,000 LOC |
```

`CLAUDE.md` is already updated.

## Proposed diff to `src/edgar/templates/config.toml` (maintainer applies by hand)

The shipped config template is hand-authored under the same rule as
`config.toml` itself (ADR-0008). Two blocks are missing. First, `[shell]
sandbox`, read and honoured by the code since M21 but never mentioned by a fresh
`edgar init`:

```diff
 [shell]
 program = "auto"
+# The walls a shell call, a command tool and the verify command run inside.
+# "none" (the default) is a plain subprocess; "bwrap" needs bubblewrap on Linux,
+# "seatbelt" uses macOS's sandbox-exec. A backend you name but do not have ends
+# the session with an error rather than running unconfined. It confines writes
+# and the network, not reads. `edgar doctor` says which is best here. [PERM-15]
+# sandbox = "none"
```

Second, `[skills]`, new in M14. It does nothing unless `[controller] enabled` is
true:

```diff
+# [skills]
+# What happens when edgar notices a run worth remembering. "propose" (the
+# default) writes the skill to .edgar/proposals/ for you to read and move
+# yourself; "auto" writes it straight into .edgar/skills/learned/, only after
+# your declared check has passed, and says so every session; "off" never calls
+# a model for this at all. Nothing here fires unless [controller] enabled is
+# true. [SKL-10, SKL-13]
+# synthesis = "propose"
+# min_tool_calls = 5     # a verified run at least this long is worth a skill
+# min_repeats = 3        # the same shape of job this often, with no skill for it
+# distill_after = 3      # bad turns recorded before edgar proposes a better body
```

## Resume commands

M14 is committed on `feat/m14-skill-synthesis`, not pushed. From that branch:

```bash
just check
```

```bash
just loc
```
