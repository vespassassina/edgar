"""Model string → provider, loaded lazily [PRV-4, PRV-9, PRV-12].

Nothing here imports an adapter at module level: `import_module` runs only when a
model string names that provider, so startup never pays for an HTTP client it
does not use. A name resolves in this order:

1. a built-in: openai, azure, openrouter, ollama, anthropic, fake
2. a `[providers.NAME]` block in config, which may also adjust a built-in
3. an `edgar.providers` entry point (v1) [PRV-14]
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from importlib import import_module
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, cast

from edgar.config.schema import Config
from edgar.core.errors import ConfigError
from edgar.providers.base import Provider

if TYPE_CHECKING:
    import httpx

_OPENAI = "edgar.providers.openai_compat"
_ANTHROPIC = "edgar.providers.anthropic"
# Five built-ins share one adapter and differ only by their row in quirks.py;
# github-copilot's own row is optional, loaded lazily from its removable file, so
# the name still resolves to this shared, non-removable adapter either way.
BUILTIN = dict.fromkeys(["openai", "azure", "openrouter", "ollama", "github-copilot"], _OPENAI)
BUILTIN |= {"anthropic": _ANTHROPIC, "fake": "edgar.providers.fake"}
KINDS = {"openai-compatible": _OPENAI, "anthropic": _ANTHROPIC}


def split(model_string: str) -> tuple[str, str]:
    """`"openrouter/openai/gpt-5"` → ("openrouter", "openai/gpt-5")."""
    name, slash, model = model_string.partition("/")
    if not slash or not name or not model:
        raise ConfigError(
            f"model {model_string!r} is not in the form provider/model",
            hint='for example --model anthropic/claude-sonnet-5, or [model] default = "…"',
        )
    return name, model


def resolve(
    model_string: str,
    config: Config | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    **options: Any,
) -> tuple[Provider, str]:
    """`"anthropic/claude-sonnet-5"` → (the Anthropic adapter, `"claude-sonnet-5"`).
    `transport` is for tests: cassettes replay through it [ADR-0009]."""
    name, model = split(model_string)
    config = config or Config()
    block = config.providers.get(name)
    module = BUILTIN.get(name)
    if block is not None and block.kind is not None:
        if module is not None and KINDS.get(block.kind) != module:
            raise ConfigError(f"[providers.{name}] kind = {block.kind!r} does not match {name}")
        module = KINDS[block.kind]
    if module is None:
        adapter = _plugin(name)  # an installed package may register the name [PRV-14]
        if adapter is None:
            known = ", ".join(sorted({*BUILTIN, *config.providers}))
            raise ConfigError(
                f"unknown provider {name!r} in model {model_string!r}",
                hint=f"known: {known}. For another server, add a [providers.{name}] block "
                'with kind = "openai-compatible" and base_url, or install a package that '
                'registers an "edgar.providers" entry point named it',
            )
    else:
        adapter = import_module(module)  # the one place a built-in adapter is imported [PRV-4]
    if module == BUILTIN["fake"]:
        return cast(Provider, adapter.make()), model

    from edgar.providers.pricing import prices
    from edgar.providers.quirks import connect, quirks_for

    quirks, key = connect(name, quirks_for(name, block), os.environ if env is None else env)
    provider = adapter.make(
        name, quirks, api_key=key, prices=prices(config.pricing), transport=transport, **options
    )
    return cast(Provider, provider), model


def _plugin(name: str) -> Any | None:
    """The `edgar.providers` entry point named `name`, tried only once nothing
    built-in or configured claims it: a package's own module, already loaded
    [PRV-14]."""
    for ep in entry_points(group="edgar.providers"):
        if ep.name == name:
            return ep.load()
    return None
