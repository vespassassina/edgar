# ADR-0053 — What 1.0 actually ships

**Status:** Accepted · 2026-09-15 · The escalation ADR-0050 said would be needed;
moves CLI-20, TOOL-14, CTX-18, CTX-2, CFG-2, ROUTE-9 and parts of CFG-5, EXT-3 and
PRV-14 from v1 to v2

## Context

ADR-0050 cut v1's four `(Should)` items a week ago, with 1,144 lines of code left
for M9, M10 and M11, and closed by naming what would happen if the cut was not
enough: "the next lever is moving a whole milestone's Must items to a later point
in the v1 series, or revisiting Option C — not silently shipping a smaller version
of a Must requirement without a further ADR." This is that ADR.

M9 is two thirds built — `agents/` (221 lines of code), routing rules,
`providers/fallback.py`, and consecutive `task` calls fanning out through
`tools/execute.py`'s `execute_many()`. It has cost 540 lines and is not finished.
`src/` measures **7,398 of 8,000**, so 602 remain.

What is still owed, estimated against subsystems already built (`agents/` 221 for
three files, `auth/` 317, `memory/` 392, `skills/discovery.py` 63 for discovery
and progressive disclosure together):

| | Estimate |
|---|---|
| Rest of M9: plan mode and `todo` (~160), SUB-9 (~50), `route explain` (~35), `agents list\|validate` (~45) | ~290 |
| M10: manifest and discovery (~100), `ext` commands (~70), hooks (~100), provider plugins (~25), skill activation and lint (~60), skill `verify` (~25), contract kit (~70), `edgar.run()` (~40), slash commands (~40) | ~530 |
| M11: `init` (~150), `doctor` (~140), `config show --resolved` (~40), `context show` (~40) | ~370 |
| **Total against 602 available** | **~1,190** |

Roughly double. Estimates are estimates, but not by a factor of two.

## Options

**A. Raise the cap to 9,000.** Rejected, and not reopened. The budget is the
project's one anti-scope-creep mechanism (ADR-0015), the maintainer's standing
rule is to simplify first and never raise a budget, and a cap that moves whenever
the work exceeds it is not a cap. ADR-0050 left this open as a last resort; it
stays shut while cheaper levers exist, and they do.

**B. Cut tooling, keep formats.** v1's promise is "extensible and remembers;
extension formats frozen". The formats are EXT-1, EXT-2, EXT-4, EXT-8 and EXT-10,
and **a format freezes by being implemented and documented, not by shipping every
command that inspects it**. So the cuts come from commands that read a format,
never from the format itself. Chosen.

**C. Cut a whole milestone.** M10 or M11 wholesale. Rejected: without M10 the
extension formats never freeze, which is what 1.0 *is*; without M11 the first ten
minutes stay broken, which is the gap already recorded as an open item.

## Decision

Nine cuts, in the order a reader would miss them least, plus a simplification pass
before any of them is relied on.

**1. Plan mode and the `todo` tool move to v2** — CLI-20, TOOL-14, CTX-18, about
160 lines of code. This is the second move (ADR-0037 took it from M5 to M9), and
the honest reading of a feature that has now missed two tiers is that it is not
part of v1 rather than that it keeps being unlucky. `sessions/<id>/plan.md`, the
pinned working-state block above the current turn, and the `TodoUpdated` event do
not exist in 1.0. `--mode read-only` is what a careful user has instead, and it
was always the mechanism plan mode wrapped.

**2. `edgar doctor` ships credentials, connectivity and the cloud-synced directory
warning** — CFG-5's other clauses (MCP servers, extensions and their required
commands, project trust, tick installation, DB integrity) move to v2, about 70
lines. M11's goal is a good first ten minutes; nothing in the dropped list is part
of a first ten minutes. `--network` goes with them, so PRV-15's guarantee is
carried by `edgar models list`, which already prints every provider's endpoint.

**3. `edgar ext validate` and `ext add` move to v2; `ext list` stays** — EXT-3
partially, about 50 lines. EXT-1 and EXT-2 still freeze the manifest and the
discovery paths, which is what third parties build against. Installing an
extension in 1.0 is copying a folder into `.edgar/extensions/`, which is what
`ext add` did anyway, and a project extension is still executable project config
needing `edgar trust` (PERM-13).

**4. `edgar.testing.contract` moves to v2** — PRV-14's last clause, about 70
lines. The entry-point mechanism stays and is what PRV-14 is for; the packaged kit
serves third-party provider authors, of whom there are currently none, and the
contract suite itself already exists in `tests/` for anyone who wants to read it.

**5. `edgar route explain` moves to v2** — ROUTE-9, about 35 lines. Routing rules
themselves (ROUTE-2, 3, 4, 6, 7, 10) ship, so behaviour is unchanged; what is
missing is the command that explains a selection. `edgar models list` still prints
what each role resolves to and why.

**6. `edgar agents list|validate` moves to v2** — about 45 lines, no requirement
ID of its own. Agents are files in `.edgar/agents/`; `ls` lists them and a broken
one fails loudly when the `task` tool loads it.

**7. `edgar config show --resolved` moves to v2** — CFG-2, about 40 lines. Config
still carries provenance internally (CFG-1, CFG-3); this is the command that
prints it.

**8. `edgar context show` moves to v2** — CTX-2, about 40 lines. Also its second
move: ADR-0038 took it from M5 to M11.

**9. A simplification pass before the remaining work, not after.** The maintainer's
standing order is simplify first, then move features, and the precedent is commit
`944efde`, which shaved 116 lines without losing a feature. `cli/` (1,864),
`tools/` (1,340) and `providers/` (1,286) are the three largest packages and the
ones that grew most incrementally. Whatever it yields is measured, not assumed:
nothing above is reinstated on the strength of an expected saving.

**What still ships in 1.0, unchanged:** the extension manifest and discovery
(EXT-1, EXT-2), `ext list`, hooks entire (EXT-4 to EXT-7, including the fail-closed
`pre_tool` veto), extension tools, skills and agents (EXT-8), `edgar.run()`
(EXT-9), the format freeze (EXT-10), the ports rule (EXT-11), provider plugins
(PRV-14's entry point), deterministic skill activation and the description lint
(SKL-17), a skill's `verify` as a verification source, subagents entire including
the multi-row status bar (SUB-1 to SUB-10), routing rules and fallback, and
`edgar init` with `edgar` offering to run it when nothing is configured (CFG-4).

## Consequences

- Demand falls from about 1,190 to about 650 against 602 available, before the
  simplification pass. That is tight rather than comfortable, and deliberately so:
  a third trim is a real possibility and would mean the v1 tier boundary, not this
  session's scope, was drawn in the wrong place.
- Seven things a reader may expect from 1.0 are not in it: plan mode, a todo list,
  a thorough `doctor`, `ext add`, the contract kit, and three introspection
  commands (`route explain`, `config show --resolved`, `context show`). Each is
  named in `docs/JOURNAL.md`'s open items.
- No format changes and no interface changes. Every cut is a command or a feature
  layered on scaffolding that still ships, so none of it forces a redesign of what
  does, and each can arrive in v2 additively — which is exactly what EXT-10's
  freeze promises.
- PRD §5.1's tier map and requirement rows, and `ROADMAP.md`'s M9, M10 and M11
  sections, move in the same change as this ADR.
