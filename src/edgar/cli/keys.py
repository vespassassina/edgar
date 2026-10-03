"""`edgar keys`: where the API keys for models and for web search are kept [CFG-6, ADR-0076]."""

# `edgar keys`              each model provider and search provider: its variable and
#                           where the key is now (environment, keyring, or nowhere)
# `edgar keys set NAME`     NAME is a provider, a search provider or a VARIABLE; the key
#                           is asked for without echo (or read from a pipe) and kept
#                           in the OS keyring as `env:VARIABLE`; it is never printed
# `edgar keys remove NAME`  forget it
#
# The key is never written to a file in the project or the config. Every lookup of
# a variable (a provider's, or `${env:NAME}` in a tool file) takes the environment
# first and the keyring second, so exporting the variable still wins.

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

from edgar.auth import store
from edgar.config.load import load
from edgar.core.errors import ConfigError, UsageError
from edgar.providers.quirks import quirks_for
from edgar.providers.registry import BUILTIN

WIZARD = Path(__file__).resolve().parent.parent / "templates" / "wizard.toml"


def _known(cwd: Path) -> dict[str, str]:
    """Name -> variable, for every model provider and search provider edgar knows."""
    from edgar.cli.models import catalog

    config = load(cwd)
    known: dict[str, str] = {}
    for name in sorted({*BUILTIN, *config.providers, *catalog()} - {"fake"}):
        try:
            var = quirks_for(name, config.providers.get(name)).api_key_env
        except ConfigError:  # a vendor in the catalog that has no block yet
            var = catalog().get(name, {}).get("api_key_env")
        if var:
            known[name] = var
    search = tomllib.loads(WIZARD.read_text(encoding="utf-8"))["search"]["providers"]
    return known | {f"search:{n}": v for n, v in search.items()}


def command(argv: list[str], cwd: Path) -> int:
    known = _known(cwd)
    if not argv:
        return _list(known)
    if argv[0] in ("set", "remove") and len(argv) == 2:
        var = known.get(argv[1]) or known.get(f"search:{argv[1]}") or argv[1]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", var):
            raise UsageError(f"{argv[1]} is not a provider or a variable name", hint="edgar keys")
        return _set(var) if argv[0] == "set" else _remove(var)
    raise UsageError("usage: edgar keys [set NAME | remove NAME]")


def _list(known: dict[str, str]) -> int:
    import os

    wide = max(map(len, known))
    for name, var in known.items():
        where = (
            "environment" if os.environ.get(var) else "keyring" if store.read(f"env:{var}") else "-"
        )
        print(f"{name:<{wide}}  {var:<26} {where}")
    print("\nedgar keys set NAME   (a provider, search:NAME, or any VARIABLE)")
    return 0


def _set(var: str) -> int:
    # 1. No keyring, no point asking: say so before the key is typed.
    if not store.available():
        raise ConfigError("there is no keyring to store this in", hint=store.MISSING)
    # 2. A terminal gets a hidden prompt; a pipe gets its first line.
    if sys.stdin.isatty():
        from getpass import getpass

        key = getpass(f"{var} (hidden): ")
    else:
        key = sys.stdin.readline()
    key = key.strip()
    if not key:
        print("nothing entered, nothing kept")
        return 1
    store.write(f"env:{var}", key)
    print(f"kept {var} in your keyring")
    return 0


def _remove(var: str) -> int:
    print(f"forgot {var}" if store.erase(f"env:{var}") else f"nothing kept for {var}")
    return 0
