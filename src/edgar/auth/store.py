"""Where a credential edgar was given lives: the OS keyring, and nowhere else
[CFG-6, ADR-0032].

`keyring` is an optional extra, so every function here works without it and says
so. A secret read back is registered for redaction the moment it is read, so it
cannot reach a transcript, an event or a log.
"""

# read(account)     the secret, or None; registers it with scrub() [TOOL-6]
# write(account, s) keep it, or raise if there is no keyring to keep it in
# erase(account)    forget it; True if there was something to forget
#
# An account is "provider:openrouter" or "mcp:<url>": one namespace, so
# `edgar logout` and `edgar mcp logout` see the same store.

from __future__ import annotations

from typing import Any

from edgar.core.errors import ConfigError
from edgar.tools.custom import SECRETS

SERVICE = "edgar"
MISSING = "install the extra that keeps secrets: pip install 'edgar-harness[keyring]'"


def _keyring() -> Any | None:
    # Imported here, never at startup: nothing on the fast path needs it (NFR-1).
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return None
    return keyring


def available() -> bool:
    return _keyring() is not None


def read(account: str) -> str | None:
    ring = _keyring()
    if ring is None:
        return None
    try:
        secret = ring.get_password(SERVICE, account)
    except Exception:  # a locked or broken keyring is a missing key, not a crash
        return None
    if secret:
        SECRETS.add(secret)
    return secret or None


def write(account: str, secret: str) -> None:
    ring = _keyring()
    if ring is None:
        raise ConfigError("there is no keyring to store this in", hint=MISSING)
    SECRETS.add(secret)
    ring.set_password(SERVICE, account, secret)


def erase(account: str) -> bool:
    ring = _keyring()
    if ring is None or read(account) is None:
        return False
    try:
        ring.delete_password(SERVICE, account)
    except Exception:
        return False
    return True
