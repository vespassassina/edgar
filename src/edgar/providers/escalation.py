"""The model that started this session is not capable enough? Walk a declared
chain upward, capped, always announced [ROUTE-5, ROUTE-10, ADR-0013].

Escalation reacts to a *pattern* of failure, never a single one: one failed tool
call is normal work; the same shape failing twice in a row, or the model losing
the tool-call format twice, means the model itself is the problem. The state
lives on `Runtime.escalation`, which the loop passes into every turn but never
recreates, so it survives the whole session, not one turn: the chain only ever
moves up, and a model already tried is never tried again [ROUTE-5].
"""

# escalate(rt, turn), once per round, after this round's tool calls ran:
#   1. disabled, or the chain and the cap are both already exhausted: nothing to do
#   2. count this round's tool errors into the running total; a round with no
#      failures at all resets the consecutive-failure count to zero
#   3. schema violations read turn.usage.repairs directly: already counted [PRV-16]
#   4. no threshold crossed: nothing to do
#   5. the next model up the chain: crossing families drops reasoning for the
#      rest of the turn [PRV-13]
#   6. announce the switch on the bus; a silent model change is not allowed [ROUTE-10]

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from edgar.core.errors import ConfigError
from edgar.core.events import Escalation
from edgar.providers.base import Provider

if TYPE_CHECKING:
    from edgar.core.loop import Runtime, _Turn

# Error kinds that mean the tool ran and failed, as opposed to never running at
# all (a validation error, a permission denial, an unknown name) [ROUTE-5].
_RAN_AND_FAILED = frozenset({"timeout", "nonzero_exit", "provider_http", "internal", "cancelled"})


@dataclass(frozen=True, slots=True)
class Triggers:
    # Each is a threshold, 0 meaning "never on this trigger" [ROUTE-5].
    tool_call_errors: int = 0
    consecutive_failures: int = 0
    schema_violations: int = 0


@dataclass(frozen=True, slots=True)
class EscalationConfig:
    """What `[model.escalation]` says, before its model strings are resolved to
    providers (the registry's job, done once in `cli/setup.py`)."""

    models: tuple[str, ...]  # weakest first; the session's own model is index -1
    max_escalations: int
    on: Triggers


@dataclass(slots=True)
class EscalationState:
    """`Runtime.escalation`: mutable on purpose, so the same instance carries its
    counters and its position in the chain across every turn the session runs.
    `current` and `after_round` are `core/loop.py`'s whole view of this file: it
    calls them structurally, matching `_Escalator`, and never imports this
    module, so `providers/escalation.py` stays removable [ROUTE-5, NFR-12]."""

    chain: tuple[tuple[str, Provider, str], ...]  # (name, provider, its model), weakest first
    max_escalations: int
    on: Triggers
    index: int = 0  # how far up the chain this session has already gone
    tool_call_errors: int = 0
    consecutive_failures: int = 0

    def current(self, rt: Runtime) -> tuple[Provider, str, str]:
        # What `_ask` should use this request: the escalated model once one has
        # been reached, the session's own model otherwise.
        if self.index == 0:
            return rt.provider, rt.model, rt.name
        name, provider, model = self.chain[self.index - 1]
        return provider, model, name

    def after_round(self, rt: Runtime, turn: _Turn) -> None:
        # The loop's whole reaction to a round of tool calls: bump the chain
        # when a trigger's threshold is crossed, or do nothing [ROUTE-5, ROUTE-10].
        if self.index >= min(len(self.chain), self.max_escalations):
            return
        if not _due(self, turn):
            return
        provider, _, from_model = self.current(rt)
        name, to_provider, _ = self.chain[self.index]
        self.index += 1
        self.tool_call_errors = self.consecutive_failures = 0
        if to_provider.family != provider.family:  # crossing families drops it [PRV-13]
            turn.reasoning = False
        reason = f"{from_model} failed repeatedly, escalating to {name}"
        rt.bus.emit(Escalation(from_model=from_model, to_model=name, reason=reason))


def _due(state: EscalationState, turn: _Turn) -> bool:
    # 1. This round's tool errors, and whether every call this round failed.
    errors = sum(1 for r in turn.results if r.error is not None and r.error.kind in _RAN_AND_FAILED)
    state.tool_call_errors += errors
    all_failed = bool(turn.results) and all(r.is_error for r in turn.results)
    state.consecutive_failures = state.consecutive_failures + 1 if all_failed else 0
    # 2. Any threshold this config sets, crossed.
    on = state.on
    return (
        (bool(on.tool_call_errors) and state.tool_call_errors >= on.tool_call_errors)
        or (bool(on.consecutive_failures) and state.consecutive_failures >= on.consecutive_failures)
        or (bool(on.schema_violations) and turn.usage.repairs >= on.schema_violations)
    )


def chain_from_config(later: dict[str, Any]) -> EscalationConfig | None:
    """`[model.escalation]` arrives in `Config.later["model.escalation"]`
    (`config/schema.py`'s `LATER`); this is where v3 finally reads it. `None`
    when the table is absent, or `enabled = false` names it off."""
    raw = later.get("model.escalation")
    if not isinstance(raw, dict) or not raw.get("enabled", True):
        return None
    chain = raw.get("chain", [])
    if not isinstance(chain, list) or not chain or not all(isinstance(m, str) and m for m in chain):
        raise ConfigError('[model.escalation] chain must be a non-empty list of "provider/model"')
    on = raw.get("on", {})
    if not isinstance(on, dict):
        raise ConfigError("[model.escalation] on must be a table of trigger = count")
    try:
        triggers = Triggers(**on)
    except TypeError as exc:
        raise ConfigError(f"[model.escalation] on: {exc}") from None
    return EscalationConfig(tuple(chain), int(raw.get("max_escalations", len(chain))), triggers)
