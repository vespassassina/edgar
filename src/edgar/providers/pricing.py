"""What a request cost [BUD-1, BUD-5].

Unknown pricing is `None`, shown as "unknown", never a wrong zero: a budget cap
that silently counts nothing is worse than one that says it cannot count. The
shipped table is small and dated; `[pricing."provider/model"]` in config adds
models or overrides these, and wins.
"""

from __future__ import annotations

from collections.abc import Mapping

from edgar.config.schema import PriceSection
from edgar.providers.base import Usage

CHECKED = "2026-09-13"  # when these were last compared with the providers' price pages

# USD per million tokens: input, output, cache read, cache write.
BUILTIN: dict[str, PriceSection] = {
    "openai/gpt-5": PriceSection(1.25, 10.0, 0.125),
    "openai/gpt-5-mini": PriceSection(0.25, 2.0, 0.025),
    "openai/gpt-5-nano": PriceSection(0.05, 0.40, 0.005),
    "anthropic/claude-opus-4-5": PriceSection(5.0, 25.0, 0.50, 6.25),
    "anthropic/claude-sonnet-4-5": PriceSection(3.0, 15.0, 0.30, 3.75),
    "anthropic/claude-haiku-4-5": PriceSection(1.0, 5.0, 0.10, 1.25),
}


def prices(configured: Mapping[str, PriceSection]) -> dict[str, PriceSection]:
    return {**BUILTIN, **configured}


def cost_of(model: str, usage: Usage, table: Mapping[str, PriceSection]) -> float | None:
    """`usage.input_tokens` counts every input token, cached ones included."""
    price = table.get(model)
    if price is None:
        return None
    read, write = usage.cache_read_tokens, usage.cache_write_tokens
    plain = max(0, usage.input_tokens - read - write)
    total = (
        plain * price.input
        + read * (price.input if price.cache_read is None else price.cache_read)
        + write * (price.input if price.cache_write is None else price.cache_write)
        + usage.output_tokens * price.output
    )
    return total / 1_000_000
