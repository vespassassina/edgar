# Handoff — start here

For the coding session picking up after v1.0. Written 2026-09-16 by the
planning session; replace it each time work stops mid-task, delete it when the
list is done. Read it first, then the three documents under "Read".

## Where things stand

- v1.0 is code-complete: M0–M11, `src/` at exactly 8,000 of 8,000 lines of
  code, 670 tests green, `just check` passes. Not tagged: the version is still
  `0.1.0`.
- The plan after 1.0 was re-tiered on 2026-09-16
  ([ADR-0057](adr/0057-daily-driver-before-learning.md)): **v2 is the daily
  driver**, M18–M22, ≤ 9,500 lines of code. Learning (M12–M15) is v3, the
  broker and scheduling (M17, M16) are v4. Milestone numbers did not change;
  the order of work is M18, M19, M20, M21, M22, then M12.
- The branch `docs/re-tier-v2-v3-v4` carries every document amendment.

## Read, in this order

1. [ADR-0057](adr/0057-daily-driver-before-learning.md): why, and the eight
   decisions. Ten minutes.
2. [`ROADMAP.md`](ROADMAP.md), section "v2 — 2.0, the daily driver", then M18.
   Every item names its files, requirement IDs, test and size.
3. [`AGENTS.md`](../AGENTS.md): the standing rules. Lines mean lines of code;
   pseudocode comments in every file you touch; shallow functions; the tour
   changes in the same commit as the code; `just check` before every commit;
   journal, changelog, roadmap status and an ADR when a decision could go
   another way.

## Step 0 — tag v1.0

Nothing in v2 starts until 1.0 is a tag, so the budget line is fixed.

1. Bump the version to `1.0.0` in both `pyproject.toml` and
   `src/edgar/__init__.py`.
2. Move the "Unreleased" section of `CHANGELOG.md` under `## 1.0.0 — <date>`,
   leaving an empty "Unreleased" above it.
3. Set M11's row in `ROADMAP.md`'s status table to "Done · 1.0".
4. `just check`; commit `release: 1.0.0`.
5. **Stop and ask the maintainer** to push, tag `v1.0.0` and publish the
   GitHub release. Pushing, tagging and releasing are theirs, never yours.
6. When the release runs, watch the `pyapp` and `docker` jobs in
   `.github/workflows/release.yml`; they have never executed. If one fails,
   fix forward with its own journal entry, and an ADR if the fix changes what
   the release ships.

## Step 0b — the dogfood week

Run in parallel with M18, which writes no `src/` code. The friction list is
M19–M22's real specification; the roadmap items are the best guess without it.

```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

```bash
uv run edgar --model ollama/qwen3:8b
```

Use edgar on edgar: ask it to read a module, fix a test, write a docstring,
run `just check`. Every time you reach for something that is not there, or
something that is there gets in the way, add a line under a `## Dogfood`
heading at the top of [`JOURNAL.md`](JOURNAL.md)'s open items: what you tried,
what happened, which M19–M22 item covers it, or "none". At the end of the week
reorder the items inside M19–M22 by that list. Do not add items; the budget
does not move.

## Step 1 — M18, tours for v1 and the map

Take the items in `ROADMAP.md` M18 in order. For each one:

1. Read the item and the files it names.
2. Write or extend the test first (`tests/unit/test_tour.py`, or the map test).
3. Build the page, stops or script.
4. `just check`. The tour test must pass for every `docs/tour/*.html`.
5. Commit with the item's name as the subject, requirement IDs in brackets.

Facts you need and might otherwise re-derive:

- `tests/unit/test_tour.py` finds stops with the regex
  `<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">`. Keep
  that exact shape on every page so one test covers all of them. The test
  also requires at least one planned stop to exist; s25–s30 in `index.html`
  stay planned until v3 and v4 build them.
- `docs/tour/index.html` is the only page today; `docs/tour/artifactkit/`
  holds the kit it links. Sibling pages link the same kit relatively.
- The map: `scripts/tour_map.py` writes `docs/tour/map.json` (one node per
  tier, package and file: `path`, `kind`, `loc` from
  `tests/support/budget.py::count_loc`, `summary` from the file's opening `#`
  comment, `stop` anchor, `status`), and `docs/tour/map.html` draws it as
  inline SVG, tree only, no flows. `just map` regenerates both; a test asserts
  the JSON matches the tree, so a new file without a regenerated map fails CI.
- The no-orphan test is the last item, after the pages exist; otherwise it
  fails on 32 files at once and tells you nothing.
- M18 adds no line to `src/`. `just loc` must still read 8,000 / 8,000.

M18 is done when: every `.py` under `src/edgar` (except `__init__.py`) appears
in some page's `data-files`; the map is current in CI; `just check` is green;
the roadmap status table says "Done" for M18 and "Next" for M19; the journal
has the entry; the changelog has a "Docs" line.

## Step 2 — M19 onward

Before the first M19 commit, in `tests/support/budget.py`, set
`TARGET_TIER = "v2"`. From then on `just loc` reports against 9,500. Then the
same loop as M18, item by item, with the milestone's tour page as its last
item. Never start M20 with M19's tour missing.

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

`CLAUDE.md` is already updated on this branch.

## Resume commands

```bash
git switch docs/re-tier-v2-v3-v4
```

```bash
just check
```

```bash
just loc
```
