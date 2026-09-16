# ADR-0058 — M18, the v1 tour pages and the map as built

**Status:** Accepted · 2026-09-16 · Completes M18, the first v2 milestone;
implements ADR-0057's "every milestone ends with its tour"; adds nothing to
`src/`

## Context

M18 is the only milestone in the plan that writes no source code. v1 shipped
whole in 1.0, but the tour still described it in five thin stops at the end of
one long page, and seventeen `.py` files under `src/edgar` had no stop anywhere.
ADR-0057 made the tour a completion condition for every milestone, so a v1 the
tour cannot explain is a v1 that was never finished.

The work was seven pieces, each committed on its own: shared `tour.css` and
`tour.js`, a page per v1 feature (`memory`, `mcp`, `agents`, `extensions`), the
Core stops that were missing, a test that fails on a source file with no stop, a
generated map of the whole harness, the stale status lines, and a header that
links every page. The LOC budget read 8,000/8,000 before and after.

Five decisions were not obvious.

## Options and decisions

**1. The map's data: hand-written or generated.** The map has to name every file,
its size and the stop that explains it. (A) Write `map.html` by hand like every
other tour page, and let `tests/unit/test_tour.py`'s size tolerance catch drift.
(B) Generate the data with a script and commit the output. **Decided: B.** The
tour's other pages describe a handful of files each and a human can reread them;
the map describes ninety-four, and a hand-written copy would be wrong within a
week. `scripts/tour_map.py` reads the stops out of the pages themselves and the
sizes out of `tests/support/budget.py`'s `count_loc` — the one counter, never
reimplemented — and `tests/unit/test_tour_map.py` regenerates it in memory and
fails on a single differing byte. The fix is always `just map`.

**2. `fetch("map.json")` does not work under `file://`.** The tour must open as
a local file; a page that only works when served is not a page you can read on a
plane. (A) Inline the JSON into `map.html` and have the generator rewrite the
page. (B) Serve the tour and document that. (C) Write the same object twice:
`map.json` for anything that wants to read it, and `map.data.js` setting
`window.EDGAR_MAP`, which a `<script src>` loads from any origin including none.
**Decided: C.** A generator that rewrites a hand-authored HTML file is the kind
of hidden behaviour this project refuses elsewhere, and both outputs come from
the same function, so the byte-match test covers them together.

**3. Tree only, no flow arrows.** The obvious next step from a tree is to draw
the call graph over it. **Decided against.** The tour already has fifteen Mermaid
diagrams for flow, and each one answers a specific question. The map answers a
different one — what is there, how big is it, which milestone brought it — and
an arrow layer would make it answer neither well. No JS library either: inline
SVG built in about sixty lines, for the same reason the harness has four
dependencies.

**4. A package's empty `__init__.py` gets no node.** Fifteen of them exist, all
empty, none with a stop. (A) Give them nodes and write fifteen filler stops. (B)
Exempt them from both the map and the no-orphan test. **Decided: B.** A leaf with
nothing to say is noise on a map whose whole point is shape. `src/edgar/__init__.py`
is not empty — it carries `edgar.run()` — and is kept. The consequence is that
the map totals 7,998 lines of code rather than 8,000, which the page states
outright rather than rounding.

**5. Which tier a file belongs to, with no per-file history to read.** Files
move, and `git log --follow` on ninety-four paths is neither fast nor reliable.
**Decided:** derive it from the tour. Everything Part I of `index.html` names is
Core by definition, so the generator carries a short hand-maintained list of the
v1 prefixes and files and treats the rest as Core, with the planned `learning/`,
`controller/`, `broker/` and `schedule/` paths as v3 and v4. It is evidence from
the document the map is part of, and it is wrong in the same direction as the
tour if the tour is wrong.

## Consequences

`tests/unit/test_tour.py::test_no_source_file_is_missing_from_the_tour` now makes
"a milestone with code and no tour is not done" a failing test rather than a
convention: a new module under `src/edgar` fails the suite until some stop names
it. `just map` must be run after any change to `src/edgar` or to a stop's
`data-files`, and the committed `map.json` and `map.data.js` are checked byte for
byte. `README.md`'s status paragraph and the tour's Part II pill describe a
released 1.0 rather than a pending one.
