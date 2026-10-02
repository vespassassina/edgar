# ADR-0071 — Aggregate size budgets pass up to 10% over

**Status:** Accepted · 2026-10-02 · Amends ADR-0040's checks, not its counting

## Context

Two features in a row (ADR-0069, ADR-0070) went over the non-removable budget
by a few dozen lines, and each time the maintainer accepted it. A red test that
is accepted every time is noise: it hides a real overage later and blocks CI and
the release workflow, which runs the whole suite.

## Decision

`tests/support/budget.py` passes the aggregate limits (the tier total, `core/`,
and the non-removable remainder) up to 10% over their budget (`MARGIN`). The
published budgets do not change. `just loc` marks a figure in the margin `MARG`.
`core/loop.py`'s 200 gets no margin: it is a shape, not a total.

## Consequences

- The non-removable budget passes to 10,450 lines of code. It sits at 9,555.
  The margin is shared by everything, so the next feature should free lines
  rather than assume the room is its own.
- `AGENTS.md` and the PRD still state the budgets without the margin. They are
  hand-authored (ADR-0007) and were not touched; the maintainer applies that
  edit.
