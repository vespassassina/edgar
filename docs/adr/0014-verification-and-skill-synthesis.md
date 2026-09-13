# ADR-0014 — Verify before done, synthesise skills only from verified work

**Status:** Accepted · 2026-09-10

## Context

Two ideas from other harnesses are worth having. Hermes Agent (Nous Research)
writes reusable skills from its own work: after complex tasks, after recovering
from errors, and after user corrections. Claude Code does not treat a task as
finished until it has been checked.

Hermes's version conflicts with two rules edgar already holds. Its background review
replays the whole conversation, tool output included, and writes memory and skills
from it. MEM-9 exists to close that channel: a README or web page with an injected
instruction can become a skill that loads in every future session. Hermes also
writes skills without approval by default, while edgar's rule is that machines
propose and people apply (MEM-2, CTRL-12).

There is a third problem Hermes does not solve: it learns from what the agent
believes worked. A model that declares success on a broken fix produces a skill
that encodes the broken fix.

Autolearn of skills must be possible, not only proposals. So the question is not
whether to allow automatic writes but under which conditions they are safe enough
to offer.

## Options

**A. Copy Hermes.** Post-turn review over the full transcript, free skill writes,
optional approval gate. Simplest to explain and the most "self-improving". Breaks
MEM-9 and MEM-2, and learns unverified procedures.

**B. Proposals only.** Synthesis always produces a diff the user applies. Keeps
every existing invariant. Nothing is learned until someone reviews it, so the tool
never grows on its own, which is the part people like about Hermes.

**C. Verified synthesis, proposals by default, opt-in automatic writes into a
machine-owned folder.** A deterministic verification gate supplies ground truth.
Synthesis sees only the outline of a run. Default mode proposes; `auto` writes
without review but only into `.edgar/skills/learned/`, only after a passing check,
and with a disclaimer.

**D. A second model judges success.** Replaces a declared command with an LLM
verdict. Works when there is no test to run. Nondeterministic, costs a call per
turn, and a model grading a model is exactly the judgement the gate exists to
replace.

## Decision

Option C.

**Verification gate** [VER-1..7]. `core/verify.py`, called from the loop at the point
where the model stops calling tools. The effective command comes from `--verify`,
then the schedule entry, agent frontmatter, loaded skills, then `verify.command`
in config. It runs only after turns that used a non-read tool. Non-zero output goes
back to the model and the loop continues, up to `verify.max_attempts` (default 2).
Authorisation happens before the turn starts, through `permissions.decide()`.
Failure after the cap is exit 9.

**Synthesis** [SKL-8..16]. Triggers are deterministic checks added to the
controller's post-turn gate, reading experience telemetry: verified success after
many tool calls, verified success after an error, a user correction, or a task shape
that keeps recurring. When one trips, the controller's cheap model receives the
outline of the run (prompt, corrections, ordered tool calls with arguments, errors,
verification result) and returns `propose_skill`, a new whitelist entry.

```toml
[skills]
synthesis = "propose"        # off | propose | auto
distill_after = 3            # HISTORY.md observations before a patch is drafted

[skills.synthesis_triggers]
min_tool_calls = 5
min_repeats = 3

[skills.curator]
enabled = false
stale_after_days = 60

[verify]
command = "just check"
max_attempts = 2
```

`propose` writes a diff to `.edgar/proposals/`. `auto` writes into
`.edgar/skills/learned/`, only for verified triggers; correction-only and unverified
turns still produce proposals, and patches to hand-authored skills are always
proposals. Each session start under `auto` prints the disclaimer in SKL-13.

**Improvement in use** [SKL-14]. Errors, corrections and failed checks in a turn that
loaded a skill append to that skill's `HISTORY.md`; `skills distill` drafts a patch
from them, under the same mode rules.

**Curator** [SKL-15]. Optional, off by default, on demand or scheduled through
`tick`. Archives, never deletes.

## Consequences

**Load-bearing: the synthesiser never sees tool output.** If a later change passes
tool results into synthesis "for better skills", the injection channel MEM-9 closes
reopens, and in `auto` mode it persists without review.

**Load-bearing: `auto` requires a passing verification.** It is what separates
"the procedure worked" from "the model said it worked". Removing it makes `auto`
Option A with extra steps.

**Load-bearing: `learned/` is the only place `auto` writes.** Hand-authored skills
stay human territory in every mode, which keeps MEM-2 true without an exception.

**Residual risk.** Tool arguments are model-authored and can carry content the model
read, so an outline is not guaranteed clean. The mitigations are layered, not
absolute: verification, the disclaimer, `[learned]` tagging, and a revert on every
write. `propose` stays the default for this reason.

**Verification changes what "done" means in pipes.** `edgar -p … --verify … && git
commit` is now meaningful, which is also why exit 9 is distinct from exit 8.

**Cost.** Verification costs a subprocess per mutating turn. Synthesis costs one
cheap-model call when a trigger trips and nothing otherwise, consistent with
ADR-0008. Roughly 300 LOC across `core/verify.py`, `skills/synthesis.py` and
`skills/curator.py`, no new dependencies, nothing on the startup path.

## Rejected alternatives

**A (copy Hermes)** is rejected on MEM-9 and MEM-2. It would be reconsidered only if
edgar gained a reliable way to separate instructions from data in tool output, which
no current technique provides.

**B (proposals only)** remains the default, but as the only mode it fails the
requirement that autolearn of skills be possible. Revisit if `auto` mode produces
skills people routinely forget.

**D (model-judged verification)** is rejected as the gate. It could return as an
opt-in *extra* check for tasks with no runnable test, but it must never satisfy the
`auto` precondition, since that would reintroduce unverified learning.

**Memory nudges, a skill hub, a messaging gateway and user modelling** from Hermes
are out of scope; see PRD §5.2.
