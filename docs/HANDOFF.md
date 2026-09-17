# Handoff — start here

For the coding session picking up after v1.0. Written 2026-09-16 by the
planning session; replace it each time work stops mid-task, delete it when the
list is done. Read it first, then the three documents under "Read".

## Where things stand

- **v1.0 is tagged and released.** `v1.0.0` is published on PyPI, `ghcr.io`
  and as GitHub release binaries for all three platforms, 723 tests green,
  `just check` passes. Step 0 below is done, including the fix-forward:
  `docker` raced `publish` on the first real run and was fixed in
  [`.github/workflows/release.yml`](../.github/workflows/release.yml)
  (`needs: [build, publish]`); see `JOURNAL.md`'s 2026-09-16 "docker raced
  publish" entry.
- **M18 is done** (2026-09-16,
  [ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md)): the tour has
  a page per v1 feature, Core's missing stops, a [map](tour/map.html) behind
  `just map`, and a test that fails on a source file with no stop. It added no
  line to `src/`.
- **M19 is done** (2026-09-17,
  [ADR-0059](adr/0059-m19-working-state-as-built.md)): `@path` attachments, plan
  mode and the `todo` tool, `edgar context show`, `edgar sessions compact ID`
  and `edgar config show --resolved`. It is the first milestone since 1.0 with
  `src/` code: `just loc` reads 8,374 of 9,500. **M20, seeing and searching, is
  next.**
- The plan after 1.0 is re-tiered ([ADR-0057](adr/0057-daily-driver-before-learning.md)):
  **v2 is the daily driver**, M18–M22, ≤ 9,500 lines of code. Learning
  (M12–M15) is v3, the broker and scheduling (M17, M16) are v4. Milestone
  numbers did not change; the order of work is M18, M19, M20, M21, M22, then
  M12.
- The re-tiering docs, M18 and M19 landed on `main`. Next up: Step 0b (the
  dogfood week, the maintainer's own task) and Step 3 (M20).

## Read, in this order

1. [ADR-0057](adr/0057-daily-driver-before-learning.md): why, and the eight
   decisions. Ten minutes.
2. [`ROADMAP.md`](ROADMAP.md), section "v2 — 2.0, the daily driver", then M20.
   Every item names its files, requirement IDs, test and size.
3. [`AGENTS.md`](../AGENTS.md): the standing rules. Lines mean lines of code;
   pseudocode comments in every file you touch; shallow functions; the tour
   changes in the same commit as the code; `just check` before every commit;
   journal, changelog, roadmap status and an ADR when a decision could go
   another way.

## Step 0 — tag v1.0 · DONE 2026-09-16

`1.0.0` is tagged, released and on PyPI, with the `pyapp` binaries and the
`ghcr.io` image. The `docker` job raced `publish` on the way and was fixed
forward; the journal entry for that day has the detail.

## Step 0b — the dogfood week

Still open. It was meant to run in parallel with M18, which is now done, so it
is the last thing standing between here and M19. The friction list is M19–M22's
real specification; the roadmap items are the best guess without it.

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

## Step 1 — M18, tours for v1 and the map · DONE 2026-09-16

Built in seven commits, `65033a2..d44f7ed`, one per roadmap item. The pages are
`docs/tour/{index,memory,mcp,agents,extensions,map}.html`, sharing `tour.css`
and `tour.js`; `scripts/tour_map.py` (`just map`) writes `map.json` and
`map.data.js`. Three tests hold it: no source file without a stop, the map
byte-matches what the generator writes, and every page's header links every
other page. `just loc` still reads 8,000 / 8,000. The decisions are in
[ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md).

What a later milestone needs to know:

- Every page uses the same stop shape,
  `<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">`, so one
  test covers all of them. A new `.py` under `src/edgar` fails the suite until
  some stop names it; `__init__.py` is exempt except `src/edgar/__init__.py`.
- Run `just map` after changing `src/edgar` or any stop's `data-files`, or the
  byte-match test fails. The generator's `V1_PREFIXES` / `V1_FILES` table is
  hand-maintained: a file a new milestone adds lands in Core unless listed.
- `map.html` reads `window.EDGAR_MAP` from `map.data.js`, not `map.json`, so it
  works opened as a local file. Both are generated from the same function.

## Step 2 — M19, working state · DONE 2026-09-17

Built in six commits, `41052a8..` on the M19 branch, one per roadmap item plus
this trace. New files: `context/attach.py`, `context/working.py`,
`tools/builtin/todo.py`, `cli/inspect.py`; the tour page is
[`tour/working.html`](tour/working.html). `TARGET_TIER` in
`tests/support/budget.py` is now `"v2"`, so `just loc` reports against 9,500 and
reads 8,374. The decisions are in
[ADR-0059](adr/0059-m19-working-state-as-built.md).

What a later milestone needs to know:

- Working state (plan, todos, the mode to give back) lives on the `Session` as
  `session.working`, **not** in the transcript. `context/builder.py`'s `build()`
  calls `place()` last to render it just above the current turn. If you add a
  compaction stage, it does not need to know about working state — but anything
  that measures the prompt does: `compact()`'s `size()` counts the rendered
  block, and a new measurer that forgets it will under-read.
- Plan mode is `session.mode == "read-only"` plus `working.previous_mode`.
  There is no plan-mode flag in `permissions/`, and there must not be one:
  `decide()` stays a pure function of tool, subject and mode. Only `/plan`,
  `--plan` and `/go` call `enter()`/`leave()`.
- The three inspection commands share `cli/inspect.py`. M22's `route explain`,
  `agents list|validate` and the rest of `doctor` belong there too, not in
  `cli/admin.py`.

## Step 3 — M20 onward

The same loop as M18 and M19, item by item, with the milestone's tour page as
its last item. Never start M21 with M20's tour missing. 1,126 lines of code are
left in the v2 budget for M20, M21 and M22; if a milestone would push past
9,500, something moves out, the budget does not move.

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
