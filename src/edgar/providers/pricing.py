"""What a request cost [BUD-1, BUD-5].

Unknown pricing is `None`, shown as "unknown", never a wrong zero: a budget cap
that silently counts nothing is worse than one that says it cannot count. The
shipped table is small and dated; `[pricing."provider/model"]` in config adds
models or overrides these, and wins.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

from edgar.config.schema import PriceSection
from edgar.providers.base import Usage

CHECKED = "2026-10-03"  # when prices.toml was last compared with the providers' price pages

# USD per million tokens: input, output, cache read, cache write. The numbers live in
# templates/prices.toml, which is data and costs no lines of code.
_FILE = Path(__file__).resolve().parent.parent / "templates" / "prices.toml"
BUILTIN: dict[str, PriceSection] = {
    name: PriceSection(**row) for name, row in tomllib.loads(_FILE.read_text("utf-8")).items()
}
_DATED = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")  # claude-haiku-4-5-20251001, gpt-5-2025-08-07


def prices(configured: Mapping[str, PriceSection]) -> dict[str, PriceSection]:
    return {**BUILTIN, **configured}


def cost_of(model: str, usage: Usage, table: Mapping[str, PriceSection]) -> float | None:
    """`usage.input_tokens` counts every input token, cached ones included."""
    # A dated id costs what its alias does; OpenRouter passes the vendor's price through.
    undated = _DATED.sub("", model)
    price = table.get(model) or table.get(undated) or table.get(undated.removeprefix("openrouter/"))
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
