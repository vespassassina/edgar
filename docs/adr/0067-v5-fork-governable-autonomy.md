# ADR-0067 — Fork v5 into a governable, fully autonomous agent

**Status:** Proposed · 2026-09-24

## Context

v4 finished the plan: Core, v1, the daily driver, learning and unattended runs
are built. The maintainer wants to go further, toward an agent that runs fully
autonomously and that an organisation can still govern. The backlog behind it:

- pluggable orchestration and reasoning strategies, including a System 1
  decider such as TypeSafe's Jev (typed decisions with confidence scores, not
  generated text);
- a swappable self-learning strategy;
- pluggable observability: tap the run, show it, audit it;
- pluggable memory;
- a sealed capability broker, out of process, enforcing policy in regulated
  environments.

What makes it unclear: several of these contradict rules edgar is built on.
PRD §3 says edgar is "explicitly not for… anyone needing an enterprise audit
story". The Never list bans a daemon or service. ADR-0006 says there is one
loop. ADR-0039 keeps the broker in-process and names the HMAC receipt's limit:
it is not tamper-evident against another process running as the user. The
line-of-code budgets exist so edgar can be read in an afternoon. Changing these
rules on `main` would break the promise made to 4.x users.

## Options

**A. Amend the rules on `main`.** One codebase, one ruleset. It breaks edgar's
positioning for everyone, including those who came for the readable harness.

**B. A new repository from the v4.0 state.** Clean separation: each repository
has one `AGENTS.md`, one PRD, one Never list. Fixes on edgar must be ported by
hand, and two histories drift apart.

**C. A long-lived v5 branch line in this repository, under a new name.** The
rules change only from v5 on, only on that line. `main` stays edgar 4.x under
today's rules. Fixes flow from `main` into the v5 line by merge. The cost: two
contradicting `AGENTS.md`, PRDs and budgets in one repository, and merge
conflicts on exactly those files.

**D. A separate package depending on edgar.** No copied code, but the amended
rules could not touch what they most need to change: the loop and the
permission path.

## Decision

**C.** Chosen by the maintainer on 2026-09-24.

1. **The line.** A long-lived branch, `v5`, cut from `main` once v4.0 is
   released. `main` keeps edgar's rules. Merges go `main` → `v5`, never back.
2. **The name.** The v5 line ships under a new name, to be chosen. It has its
   own PyPI distribution and a tag prefix of its own (`<name>-v*`), so its
   versions cannot collide with edgar's `v*` tags or trigger edgar's release
   workflow.
3. **Autonomy.** No human prompt at run time. A human writes policy up front;
   an external governor decides every action the policy covers; anything
   uncovered is denied and recorded. Fail closed: a governor that is
   unreachable, slow or broken denies.
4. **Rules amended on the v5 line only:**
   - **Audience (PRD §3).** Regulated teams become a target, with an audit
     story.
   - **The Never list.** A governor process or service is allowed, owned by
     the organisation, running under an identity the agent cannot act as.
   - **One loop (ADR-0006).** Orchestration and reasoning strategies may be
     plugged in, including a System 1 decider.
   - **The line-of-code budget.** A new budget for the v5 line, set in the tier
     ADR that opens it.
5. **Rules kept on the v5 line, because they make autonomy governable:**
   - **No hidden behaviour.** A governor can only rule on what it can see.
     Every decider, strategy and learner call is an event.
   - **Machines tighten, never widen.** "Humans widen" becomes "policy written
     by a human widens". No model, strategy, decider, learner or plugin may
     widen it.
   - **The learning boundary (ADR-0017, ADR-0065).** A swappable self-learning
     strategy may change how it learns, never what it reads or where it writes.
   - **Nothing on the authorisation path is a model.** A System 1 decider
     advises routing, strategy choice and learning triggers; it never feeds
     `decide()`, a ticket or the governor.
   - **Done means verified**, and tool failures return to the model.
6. **`AGENTS.md` on the v5 line** is hand-edited by the maintainer. Agents
   propose the diff (ADR-0007, ADR-0008).

## Consequences

- Load-bearing: the governor is the only way authority reaches an autonomous
  run. If a strategy, plugin or learner can grant itself a tool call the
  governor did not see, the design is broken.
- Load-bearing: fail closed. A governor timeout that allows is a hole.
- The in-process broker (ADR-0039) becomes one adapter on the v5 line, and the
  external governor is another. The `capability-broker` prototype, whose
  DESIGN.md already names Ed25519 and distribution as next steps, is the
  natural home of the governor.
- Merges from `main` into `v5` will conflict on `AGENTS.md`, `docs/PRD.md`,
  `docs/ROADMAP.md` and `tests/support/budget.py`. The v5 line's versions of
  those files win.
- Sealing edgar governs edgar only. A person with a shell can run other tools;
  real enforcement in a regulated environment also needs OS and network
  controls. The v5 line's job is to not be the gap, and to leave a record
  someone else can verify.
- Before any v5 code: a tier ADR (budget, milestone order), a v5 PRD with
  acceptance criteria, and a plan, per the maintainer's design, spec, plan,
  test order.

## Rejected alternatives

- **A, amend `main`.** Revisit only if edgar 4.x stops being maintained as the
  readable harness.
- **B, a new repository.** Revisit if merges from `main` into `v5` cost more
  than porting fixes by hand, or once the two rulesets have drifted so far that
  shared history no longer helps.
- **D, a dependent package.** Revisit if edgar's core grows ports for strategies
  and external vetoes under its own rules, so the amended rules no longer need
  to touch the core.
- **Keep the name edgar.** The promise differs; one name would blur it for
  4.x users.
- **Deny and queue for a human, or ask a human only to widen.** Both keep a
  person in the run-time loop, which is not fully autonomous. Revisit if a
  regulated user requires a human approval step the policy cannot express.
