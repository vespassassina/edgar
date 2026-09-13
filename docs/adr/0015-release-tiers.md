# ADR-0015 — Ship in three tiers: Core, v1, v2

**Status:** Accepted · 2026-09-13 · Amends NFR-4 and the roadmap

## Context

The v0.2 spec asked for 154 Must requirements inside 8,000 lines of source and eight
dependencies: a REPL, two adapters for five providers, an MCP client, permissions,
compaction, subagents, a controller, skill synthesis with a curator, autolearn with
contradiction detection, history condensing, telemetry, routing with escalation and
fallback, a cron scheduler with three OS installers, budgets and layered config.

The stated goal is a harness that is **lightweight, extensible, open and easy to
use**. A single v1 with that feature list fails "lightweight" in one of two ways:
it overshoots the size budget, or it ships thin versions of the hard parts to fit.
Either outcome costs the teaching goal, because the parts people come to read are
exactly the ones that get thinned.

What makes this non-obvious is that none of the features are wrong. Each has an ADR
and a reason. The question is order and the promise attached to each release.

## Options

**A. One v1, as specified.** Maximum ambition, one launch. Most likely outcome is a
long run to a large release, with the budgets quietly abandoned.

**B. Cut features.** Drop the controller, synthesis and scheduling permanently.
Smallest codebase. Throws away the most interesting design work, and the learning
layer is a real differentiator.

**C. Three tiers with a hard seam.** Core is the smallest honest harness. v1 makes
it extensible and gives it memory. v2 adds the parts that learn and run unattended.
Each tier is a release with its own size budget, and v2 is built so that deleting it
leaves a working v1.

## Decision

Option C.

| Tier | Promise | Contents | Source budget |
|---|---|---|---|
| **Core** (0.x) | A harness you can read in an afternoon and use every day | loop, messages, events, sessions and resume, verify gate, cancellation; fake + two adapters for five providers plus user-defined OpenAI-compatible endpoints; built-in tools; custom command and HTTP tools; skills; permissions with taint, control files and project trust; staged context compression; `-p`, `--json`, `--events`, REPL, status line; layered config; SQLite for sessions, grants and trust | ≤ 5,000 LOC |
| **v1.0** | Extensible and remembers. Extension formats are stable from here | facts memory with `/remember` and `recall`, session search; MCP client; subagents with fan-out; routing rules and fallback; extensions, hooks, provider plugins, the `edgar.run()` embedding API; `init`, `doctor`, `config show`; full docs | ≤ 8,000 LOC total |
| **v2.0** | Learns and runs unattended | controller; autolearn, `history.md`, experience telemetry, `stats`; skill synthesis, distill, curator; escalation, `route suggest`, budget-aware downgrade; scheduling with `tick` and `schedule_self`; MCP OAuth | ≤ 11,000 LOC total |

`core/` stays ≤ 2,000 LOC in every tier [NFR-3].

**The seam.** v2 code lives in three packages, `edgar.controller`, `edgar.learning`
and `edgar.schedule`, plus `providers/escalation.py`. Core and v1 modules never
import them. They attach through two existing extension points: the event bus
(ADR-0011) and the post-turn gate in the loop. A CI test asserts the import rule,
and a second CI job deletes the v2 packages and runs the v1 suite [NFR-12].

**Semver meaning.** 0.x may change anything. 1.0 freezes the formats people build
on: tool TOML, `SKILL.md` handling, agent frontmatter, `extension.toml`, hook
events and their JSON, `--json` and `--events` output, the `Provider` protocol, and
`edgar.run()`. v2 adds to them and does not change them.

## Consequences

- **Core is shippable on its own**, and that is the point: people can use and fork
  edgar months before the learning layer exists
- **Invariants apply from the tier their mechanism lands in.** The learning
  boundary (ADR-0017) is written now but first bites in v1 (`remember`) and fully
  in v2 (autolearn, synthesis)
- **Load-bearing: v2 must stay removable.** If a Core module starts importing
  `edgar.learning` "just for telemetry", the tiers collapse back into Option A. The
  import test is what holds this line, and the event bus is what makes it cheap to
  hold: telemetry is a subscriber, not a call site
- **The roadmap is regrouped** into M0–M6 (Core), M7–M11 (v1), M12–M16 (v2)
- **Requirement IDs do not change.** The PRD maps IDs to tiers in §5.1 rather than
  renumbering, so existing references stay valid
- **Budgets are design constraints, not estimates.** A Core that needs 6,000 lines
  is a Core doing too much, and the answer is to move something to v1

## Rejected alternatives

**A (one v1)** is rejected because the budget and the feature list cannot both
hold, and the spec gives no rule for which one yields. Tiers are that rule.

**B (cut features)** is rejected because the learning layer is designed carefully
and well defended (ADR-0008, ADR-0014). It is deferred, not dropped. Revisit if v1
adoption shows nobody wants unattended or self-improving runs.

**Two tiers (Core, then everything)** was considered. It leaves the extension
formats unfrozen until the largest release, which is the wrong way round for a
project whose second audience builds on it.
