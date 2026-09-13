"""`edgar models list`: what this config can reach, without contacting anything.

It prints the model each role resolves to, and every provider with its endpoint
and key variable, so where prompts go is a question the config answers [PRV-15].
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from edgar.config.load import load
from edgar.config.schema import Config
from edgar.core.errors import ConfigError
from edgar.providers.quirks import ANTHROPIC, quirks_for
from edgar.providers.registry import BUILTIN
from edgar.providers.routing import Role, RoutingContext, select_model

ROLES: tuple[Role, ...] = ("main", "compactor", "controller", "condenser")


def list_models(cwd: Path, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    config = load(cwd, env=env)
    out = sys.stdout
    if config.model.default is None:
        out.write("model: none configured (--model provider/model, or [model] default)\n")
    else:
        for role in ROLES:
            chosen = select_model(RoutingContext(role=role), config.model)
            out.write(f"{role:<11} {chosen.model:<36} {chosen.reason}\n")
    out.write("\n")
    for name in sorted({*BUILTIN, *config.providers} - {"fake"}):
        out.write(f"{name:<11} {_describe(name, config, env)}\n")
    return 0


def _describe(name: str, config: Config, env: Mapping[str, str]) -> str:
    block = config.providers.get(name)
    if name == "anthropic" or (block is not None and block.kind == "anthropic"):
        url, url_env = (block and block.base_url) or ANTHROPIC.base_url, None
        key_env = (block and block.api_key_env) or ANTHROPIC.api_key_env
    else:
        try:
            quirks = quirks_for(name, block)
        except ConfigError as exc:
            return f"({exc})"
        url, url_env, key_env = quirks.base_url, quirks.base_url_env, quirks.api_key_env
    if not url:
        url = f"${url_env}" + ("" if env.get(url_env or "") else " (unset)") if url_env else "?"
    key = f"${key_env} ({'set' if env.get(key_env) else 'unset'})" if key_env else "no key"
    return f"{url:<36} {key}"
