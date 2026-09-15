"""Provider unreachable? Try the next model in the declared chain, sideways
[ROUTE-7, ROUTE-10, ADR-0013].

Retries and backoff already happened inside `stream()` (`providers/http.py`):
a `ProviderError` reaching the loop means that is exhausted, or the failure
was never retryable (an auth error, say). Fallback reacts to that error by
moving to the next model, never by re-implementing backoff, and it never
picks a candidate that covers less than the turn needs [ROUTE-10].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from edgar.core.errors import ConfigError, ProviderError
from edgar.core.events import EventBus, Fallback
from edgar.providers.base import Capabilities, Provider


@dataclass(frozen=True, slots=True)
class Candidate:
    model: str  # "provider/model"
    family: str  # a Provider's own `family`
    capabilities: Capabilities


@dataclass(frozen=True, slots=True)
class FallbackResult:
    model: str
    reasoning: bool  # False once the switch crosses families [PRV-13]
    reason: str  # rendered in the `Fallback` event


class NoFallback(Exception):
    """Every candidate in the chain was already tried, or none covers the turn."""


def choose(
    failed: Candidate,
    chain: tuple[Candidate, ...],
    *,
    tried: frozenset[str],
    tools_required: bool,
) -> FallbackResult:
    # 1. Walk the declared chain in order, skipping what already failed.
    for candidate in chain:
        if candidate.model == failed.model or candidate.model in tried:
            continue
        # 2. Never fall back to something that covers less than this turn needs.
        if tools_required and not candidate.capabilities.tools:
            continue
        # 3. Crossing families drops foreign reasoning rather than mis-render
        #    it downstream; staying in the same family keeps it [PRV-13].
        reasoning = candidate.family == failed.family
        reason = f"{failed.model} unreachable, falling back to {candidate.model}"
        return FallbackResult(candidate.model, reasoning, reason)
    raise NoFallback(f"no fallback left for {failed.model!r}, already tried {sorted(tried)}")


def next_provider(
    failed_name: str,
    failed_provider: Provider,
    exc: ProviderError,
    chain: tuple[tuple[str, Provider, str], ...],
    tried: set[str],
    *,
    tools_required: bool,
    bus: EventBus,
) -> tuple[Provider, str, str, bool]:
    """The loop's whole reaction to a `ProviderError`: pick the next (provider,
    model, name, reasoning) to retry with, or re-raise `exc` once `chain` is
    exhausted [ROUTE-7]. `tried` is mutated so the caller's turn stays in sync."""
    tried.add(failed_name)
    failed = Candidate(failed_name, failed_provider.family, failed_provider.capabilities)
    candidates = tuple(Candidate(n, p.family, p.capabilities) for n, p, _ in chain)
    try:
        chosen = choose(failed, candidates, tried=frozenset(tried), tools_required=tools_required)
    except NoFallback:
        raise exc from None
    bus.emit(Fallback(from_model=failed_name, to_model=chosen.model, reason=chosen.reason))
    provider, model = next((p, m) for n, p, m in chain if n == chosen.model)
    return provider, model, chosen.model, chosen.reasoning


def chain_from_config(later: dict[str, Any]) -> tuple[str, ...]:
    """`[model] fallback = [...]` arrives in `Config.later["model.fallback"]`
    (`config/schema.py`'s `LATER`); this is where v1 finally reads it."""
    raw = later.get("model.fallback", [])
    if not isinstance(raw, list) or not all(isinstance(m, str) and m for m in raw):
        raise ConfigError('[model] fallback must be a list of "provider/model" strings')
    return tuple(raw)
