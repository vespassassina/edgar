# ADR-0040 — Write the code to be read: pseudocode comments, shallow functions, lines of code, a tour

**Status:** Accepted · 2026-09-14

## Context

edgar's promise is that you can read it in an afternoon. Until now that rested on
size alone: a 5,000-line Core, and a loop under 200 lines. The maintainer asked for
more than size. Every file should narrate itself in plain comments, close to
pseudocode, so it reads fluently. Functions should stay shallow and avoid
recursion. There should also be a guided tour of the repository, with diagrams,
that points at the real files and stays in sync with them.

Two existing rules pulled the other way:

- `AGENTS.md` allows comments "only where the code cannot explain itself".
- `core/loop.py` was budgeted in *physical* lines (≤ 200), so it would fit on a
  couple of screens. With a pseudocode header and numbered steps it grew to 284
  physical lines, while its code grew by only 19 lines.

What made this unclear: "lines" meant lines of code in one budget and physical
lines in another. Counted in physical lines, every comment written for the reader
costs budget, which pushes the code toward being terse and harder to read.

## Options

**A. Keep physical lines for the loop, and comment sparingly.** The loop keeps
fitting on two screens. It cannot carry a pseudocode walkthrough without giving up
code, and it makes explaining look expensive.

**B. "Lines" means lines of code everywhere; comments are free.** Every budget
counts non-blank lines that are not only a comment. Docstrings count, since they
are text inside the code. Narration goes in `#` comments.

**C. Narrate in docstrings.** They are visible to `help()`, but they count against
the budget and make the file look larger than its logic.

For the tour:

**D. Markdown in `docs/`.** It renders on GitHub with Mermaid diagrams, and it has
one layout.

**E. A static HTML page on GitHub Pages.** It can be split by tier with a contents
list, keep per-reader progress and a reading clock, and have a link of its own in
the repository's About box.

## Decision

**B and E.**

1. **Every "lines" limit means lines of code.** A line of code is a non-blank line
   that is not only a comment; docstrings count. The Core budget is 5,000 lines of
   code, `core/` 2,000, and `core/loop.py` 200. `tests/support/budget.py` counts
   them all with one function, `count_loc`. Documents say "lines of code" wherever a
   limit is stated.
2. **Pseudocode comments in every file touched.** A file with a flow opens with a
   comment block that gives that flow as pseudocode. Long functions number their
   steps (`# 1. …`, `# 2. …`), and the numbers match the diagrams in the tour. Data
   types say in a comment what each field is for and who writes it. Narration uses
   `#` comments, not docstrings.
3. **Shallow functions, no recursion where a loop works.** A top-level function
   reads as a list of steps. Each step with any detail is a helper one level down,
   and helpers do not call each other. State one operation shares goes in a small
   mutable dataclass instead of long parameter lists: `_Turn` in `core/loop.py` is
   the pattern. Walking a tree uses an explicit stack or a library walk, not
   recursion.
4. **A Tour of the Harness.** The page lives at `docs/tour/index.html`. It has three
   parts (Core, v1, v2), each stop linking to the file on GitHub and naming the
   functions to look for. `.github/workflows/tour.yml` publishes it to GitHub Pages,
   at <https://vespassassina.github.io/edgar/>, on every push to `main` that
   changes it. `tests/unit/test_tour.py` fails when:
   - a linked file is gone;
   - a name under "Look for" is no longer defined in its stop's files;
   - a package's size in the table drifts more than 100 lines of code;
   - a package has no row;
   - a planned stop's file exists while the stop still says planned;
   - the turn diagram's step numbers stop matching `run_turn`'s comments.

## Consequences

- `core/loop.py` became `run_turn` plus five helpers (`_start`, `_capped`, `_ask`,
  `_run_tools`, `_check`) around `_Turn`. The split cost 19 lines of Core, from
  4,806 to 4,825 of 5,000, which leaves M6 about 175 lines. The loop is 189 of its
  200 lines of code and 284 physical lines.
- **Load-bearing:** the loop's 200-line limit is now lines of code. A loop with
  more than 200 lines of code still fails the build, however it is commented.
- `AGENTS.md` is hand-authored (ADR-0007), so the matching change to its comment
  rule and the loop's limit went to the maintainer as a patch, which they applied
  on 2026-09-14.
- Comments can go stale in a way code cannot. Numbered steps are checked against
  the tour's turn diagram; everything else relies on review, and on the rule that
  comments change in the same commit as the code.
- The tour page loads Mermaid from jsDelivr, pinned to an exact version, as the
  classic (UMD) build so the page also works opened as a local file. Without the
  network the diagrams show as their source text, which is still readable. A label
  that opens with "1. " is read by Mermaid as a Markdown list and cannot be drawn,
  so the steps are written "1 · ", and a test checks for it.
- **Amended the same day:** the page is styled with the maintainer's own kit,
  [artifactkit](https://github.com/vespassassina/artifactkit) (MIT), on a dark,
  desaturated midnight-blue theme. Its three stylesheets are vendored in
  `docs/tour/artifactkit/`, unchanged except the theme block, and linked rather than
  inlined, so the page's source stays short enough to read and edit by hand.
  artifactkit's `validate.mjs` is written for single files you email, so it reports
  the linked stylesheets, the Mermaid script and the raw `localStorage` keys as
  errors. For a page hosted on Pages they are expected: the keys are prefixed with
  `edgar-tour:` by hand, since every github.io page shares one storage.
- A new milestone that adds a module turns its planned stop into a built one, in
  the same commit. The test forces this.

## Rejected alternatives

**A**, because it turns explaining into a cost and the repository is meant to
teach. It would be worth revisiting only if comments started to outgrow the code in
a way that made files harder to read, not easier.

**C**, because docstrings count as code, and a teaching comment should not compete
with a feature for budget.

**D**, because the maintainer asked for HTML, and a page per tier, with progress
and a clock, does not fit in Markdown. If Pages became a burden, the same page
could be served straight from the repository with no loss of content.

A tour generated from the source by a build script was also considered. A
hand-written page with fixed hooks, checked by a test, needs no build step and no
generator to maintain.
