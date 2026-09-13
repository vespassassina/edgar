# ADR-0037 — Core stays under 5,000 lines: simplify first, then move four features to v1

**Status:** Accepted · 2026-09-13 · Amends ADR-0015 (tier contents), ADR-0025 (working state is v1), ADR-0032 (`edgar login` lands with MCP OAuth)

## Context

After M3, Core stood at 4,415 of its 5,000 lines, with M5 (context, compaction,
sessions) and M6 (skills, release) still to build, an estimated 700 to 800 lines
between them. The roadmap's rule is that the budget does not move; features do.
The maintainer confirmed it: Core stays Core, and the limit stays 5,000. "Read it in
an afternoon" is only true while the budget holds.

## Decision

**First, simplify what exists.** A review of the largest modules took out 116
lines, and nothing a user can do was lost:

- Anthropic became a row in the quirks table. One `connect()` checks the endpoint
  and the key for every HTTP provider, and both adapters lost their `make()`.
  The one change a user can see: a `[providers.anthropic]` block that sets keys
  only OpenAI-compatible servers use is now ignored instead of rejected.
- The fake provider's scripting (scripted steps, delays, stalls, injected errors)
  moved to `tests/support/scripted.py`. The product keeps only the rule-based
  `fake/test` model.
- `read` and `ls` use the same schema helper as the other built-ins.

**Then move four features to v1**, chosen because each stands on its own and no
Core feature depends on it:

| Feature | Requirements | To |
|---|---|---|
| Plan mode and the `todo` tool, pinned as working state | CLI-20, TOOL-14, CTX-18 | M9, beside subagents |
| `/save`, `/load` of a saved file, `edgar --load` | CLI-25 (those parts) | M7, with session search |
| `edgar login` | PRV-18 | M8, sharing its OAuth code with MCP servers |
| The daily cost cap | BUD-2 (daily) | M7, which can sum across sessions |

**Core keeps:** sessions as JSONL with `--resume`, `--continue` and
`/load ID`; staged compaction; `/reset`, `/undo`, `/retry`, `/history`, `/title`,
`/sessions`; `personality.md`; turn and session cost caps with exit 6; skills;
and the Core release.

## Consequences

- Core has 701 lines left for M5 and M6. M5 should take about 450 and M6 about
  200; if one runs over, the next candidates are `/history` and `edgar context
  show`, in that order.
- The loop (182 of 200 lines) gains the budget check and compaction as calls
  into collaborators, never as inline logic.
- A Core user who wants a plan writes it in the prompt or in a file, and asks
  edgar to follow it.
