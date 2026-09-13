# ADR-0008 — Controller: deterministic triggers, typed proposals, tighten-only

**Status:** Accepted · 2026-09-02

## Context

The brief asks for "an ai controller subagent that triggers on turn end to
optimize, policy, clean output and config (eg runs compact)". This is the most
interesting mechanism in the design and the easiest to turn into a footgun.

Two problems with the naive reading:

**Cost and latency.** An LLM call after every turn adds cost and delay to every
single interaction, including the ones that were fine.

**Authority.** A cheap model with repeated licence to modify config and policy
produces drift you cannot explain three days later, and if it can loosen policy it
can escalate its own permissions.

## Options

**A. Deterministic triggers, LLM only when one fires.** Plain Python checks after
each turn; the controller model runs only when something is actually wrong. Cheap,
predictable, testable with a fake clock and no provider at all.

**B. LLM every turn.** More adaptive, catches things you did not think to
threshold. Costs a call per turn.

**C. Deterministic by default, opt-in always-on.**

## Decision

Option C, with a hard safety envelope that matters more than the trigger choice.

**Deterministic checks after every turn:** token fraction of context window,
consecutive error streak, budget burn rate, output size, wall-clock. Pure functions
over session state. Zero cost when nothing trips, which is the common case.

**When a check trips**, a small model is invoked with a session summary and a
**hard-limited tool set**. It cannot call arbitrary tools.

**It returns a typed proposal** from a fixed whitelist. Nothing else parses:

```
compact · learn · switch_model · tighten_policy · warn_user · abort ·
propose_instruction · noop
```

**Safety envelope:**

- Proposals are schema-validated; malformed ones are discarded and logged
- Config and policy changes are **dry-run by default**
- Every mutation is logged with before/after and a working revert path
- **Policy may only tighten, never loosen** [CTRL-8]
- Controller failure **never fails the turn** [CTRL-11]
- The controller runs on a separately configured cheap model [CTRL-9]

## Consequences

**Tighten-only is the load-bearing rule.** Without it, a controller that
misinterprets a situation, or one influenced by injected content in the session,
can grant itself or the main agent permissions the user never approved. With it,
the worst case is an over-restricted session the user can loosen manually.

**The whitelist makes the controller testable.** Its entire output space is seven
shapes, each with a schema, so the apply path can be exercised exhaustively with
fabricated proposals and no model.

**Deterministic gating makes the common path free.** A healthy session never
invokes the controller, so the feature costs nothing until it is needed.

**Never failing the turn** matters more than it sounds: a housekeeping mechanism
that can break your session is worse than no housekeeping at all. Controller
exceptions are caught, logged, and swallowed.

**`edgar controller log` and `revert <id>`** are required surface [CTRL-10]. A
self-modifying system without an audit trail and an undo is not something a person
should be asked to trust.

**The controller may never write `AGENTS.md`** (resolves OQ-2, amended 2026-09-02).
Hand-authored files are off limits to every machine writer (ADR-0007) and the
controller is not an exception.

The reason is sharper than general principle: `AGENTS.md` is part of what
*constrains* the controller. A controller that can edit its own constraints is a
loop with no fixed point, and the failure is silent — nothing breaks, the rules
just quietly drift until behaviour no longer matches anything the user wrote.

Instead, `propose_instruction` is added to the whitelist. It emits a unified diff
against `AGENTS.md` which is shown to the user, written to
`.edgar/proposals/<id>.diff`, and applied only by an explicit
`edgar controller apply <id>`. The same rule covers `config.toml`: the controller
proposes, the human applies. [CTRL-12]

## Rejected alternatives

**Always-on LLM control** is available as an opt-in flag for users who want maximum
adaptivity and will pay for it, but it is not the default because most turns need
nothing.

**Giving the controller full tool access** was rejected immediately. A cheap model
with a broad mandate and full tools is an unbounded risk for a bounded benefit.
