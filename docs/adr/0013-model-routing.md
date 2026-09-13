# ADR-0013 — Model routing, escalation and fallback are three separate mechanisms

**Status:** Accepted · 2026-09-02

## Context

"Use different models for different scopes" was in the original brief. What the
design delivered was **static role binding**: a model for the main agent, one for
the controller, one for condensing, one for compacting, and one per subagent
declared in frontmatter (ADR-0006). Plus a `switch_model` proposal the controller
can make (ADR-0008).

That covers *scope* but not *task*. There is no answer to "this particular request
is trivial, use the cheap model", or "the local model just failed twice, try the
strong one", or "Azure is down, use OpenRouter". Those three sound like the same
feature and are routinely implemented as one. They are not the same feature.

## The distinction

| Mechanism | Question | When decided | Direction | Trigger |
|---|---|---|---|---|
| **Routing** | Which model should start this task? | Before the turn | n/a | Declarative rules over task context |
| **Escalation** | The model is not capable enough | Mid-session | Upward only | Repeated failure |
| **Fallback** | The model is not reachable | Per request | Sideways | Provider error |

Conflating them produces predictable bugs. A fallback that escalates burns money
on an outage. An escalation that behaves like a fallback silently downgrades
capability. A router that handles provider errors retries the wrong thing.

## Options considered

**A. Static roles only.** What exists today. Simple, zero cost, no surprises.
Cannot adapt to task difficulty, cannot survive an outage, cannot recover from a
weak model failing.

**B. LLM router.** A cheap model classifies each request and picks. Adaptive,
handles cases you did not anticipate. Costs a model call *per turn*, adds latency
to every interaction, and makes routing non-deterministic and hard to explain.
This is the same objection that made the always-on controller opt-in (ADR-0008).

**C. Declarative rules, pure function.** Rules in config, first match wins, over a
small fixed set of conditions. Zero cost, deterministic, explainable,
exhaustively testable.

**D. Learned routing.** Experience telemetry decides. Interesting, and it makes
behaviour depend on invisible history, which is the opposite of what a teaching
repo wants.

## Decision

**Option C for routing**, with escalation and fallback as separate, explicitly
guarded mechanisms. Option D contributes *recommendations only*, never automatic
switching.

### Routing — a pure function

```python
# providers/routing.py
def select_model(ctx: RoutingContext, rules: list[Route], defaults: ModelDefaults) -> Selection: ...

@dataclass(frozen=True)
class RoutingContext:
    role: Literal["main", "subagent", "controller", "condenser", "compactor"]
    agent: str | None
    mode: PermissionMode
    tools_required: bool
    prompt_tokens: int
    budget_remaining_fraction: float
    tags: frozenset[str]
    schedule: str | None

@dataclass(frozen=True)
class Selection:
    model: str
    rule: str          # which rule matched, or "default"
    reason: str        # human-readable, for `edgar route explain`
```

Eight conditions, deliberately. Enough to be useful, few enough that the matrix
can be tested exhaustively and a user can hold them in their head. First match
wins, same evaluation shape as `permissions.decide()` so there is one pattern to
learn rather than two.

```toml
[[route]]
name = "local-for-exploration"
when = { agent = "explorer" }
model = "ollama/qwen3"

[[route]]
name = "cheap-for-short-readonly"
when = { mode = "read-only", prompt_tokens_lt = 500 }
model = "openai/gpt-5-mini"

[[route]]
name = "downgrade-before-abort"
when = { budget_remaining_lt = 0.15 }
model = "openai/gpt-5-mini"
```

### Escalation — capability failure, upward, capped

```toml
[model.escalation]
enabled = true
chain = ["openai/gpt-5-mini", "openai/gpt-5", "anthropic/claude-opus-4"]
max_escalations = 1
on = { tool_call_errors = 2, consecutive_failures = 2, schema_violations = 2 }
```

Deterministic triggers, same pattern as the controller. Upward only. Capped, or a
struggling task walks the chain to the most expensive model and stays there.
**Always announced** via an event and the status bar — a silent model change makes
cost and behaviour inexplicable.

### Fallback — availability failure, sideways, capability-preserving

```toml
[model.fallback]
"openai/gpt-5" = ["azure/gpt-5", "openrouter/openai/gpt-5"]
```

Triggered by provider errors that retry cannot fix: auth failure, sustained 5xx,
exhausted 429 backoff. **Fallback targets must declare capabilities at least equal
to the original.** Falling back mid-turn to a model without tool support produces a
transcript the provider will reject and a session the user cannot resume.

### Learned routing — recommendations only

Experience telemetry already records task shape, model, outcome and cost [MEM-18].
`edgar route suggest` analyses it and prints candidate rules with the evidence
behind them. It never writes config. The user copies what they agree with.

Consistent with the memory design (ADR-0007): the machine proposes, the human
decides, and behaviour never changes because of history the user cannot see.

## Consequences

**Routing costs nothing.** A pure function over config, evaluated once per turn.
No model call, no network, no latency. This is why B was rejected.

**`edgar route explain` is required surface** [ROUTE-9]. Given a task context it
prints the selected model, the matching rule and the reason. Without it, rule
interaction becomes guesswork the moment there are more than three rules.

**Capability validation happens at selection, not mid-turn** [ROUTE-6]. A rule
routing a tool-requiring task to a model without tool support is a hard error with
a clear message, raised before the request. Discovering it mid-stream produces a
confusing failure.

**Budget-aware downgrade interacts with BUD-3.** A cap that would abort the run can
instead route to a cheaper model first. Degrading is usually better than stopping,
but only if it is visible, so the downgrade emits a warning.

**The controller's `switch_model` is constrained by this** [CTRL-4, ROUTE-8]. It
may only select from the escalation chain or a routing rule's target, never an
arbitrary model string. Otherwise the controller becomes an unaudited path around
the routing policy, and a proposal-whitelist that lets you name any model is not
much of a whitelist.

**Three mechanisms means three sets of tests**, and this is the point: the property
tests can assert that escalation never moves down the chain, fallback never reduces
capabilities, and routing is stable for identical inputs.

**Teaching value.** The routing/escalation/fallback distinction is one of those
things that is obvious once stated and invisible until it is. Writing all three
out separately, with different triggers and different guards, is worth more than
a single clever `pick_model()`.

## Rejected alternatives

**LLM router (B)** costs a call per turn for adaptivity most sessions do not need.
If it is ever wanted, it fits as one more routing rule kind rather than a
replacement, and it should be opt-in like the always-on controller.

**Automatic learned routing (D)** was rejected because behaviour that changes based
on invisible history is exactly what makes an agent tool feel unpredictable. The
`route suggest` half keeps the value and drops the surprise.

**More conditions.** Time of day, file types touched, git branch, day of week were
all considered and cut. Eight conditions is already a matrix; sixteen is a
configuration language nobody will test.
