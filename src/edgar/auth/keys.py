"""`edgar login PROVIDER`: a provider that hands out an API key through OAuth
hands it to you, not to edgar [PRV-18, ADR-0032].

The key is yours, revocable where you made it, and it goes to the OS keyring or,
with no keyring installed, is printed once and stored nowhere. edgar never signs
in with anyone's subscription.
"""

# login(name, quirks, say)  the browser flow, then the exchange, then the keyring
# stored(name)              a key kept from an earlier login, for connect()
# logout(name)              forget it here; revoking it is done where it was issued

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from edgar.auth import oauth, store
from edgar.core.errors import ConfigError


def account(name: str) -> str:
    return f"provider:{name}"


def stored(name: str) -> str | None:
    return store.read(account(name))


def logout(name: str) -> bool:
    return store.erase(account(name))


async def login(name: str, row: Any, say: Callable[[str], None]) -> str:
    """Sign in to `name` and return the key it issued. `row` is its `oauth` table."""
    # 1. A verifier this process keeps and a challenge the provider sees, so the
    #    code that comes back through the browser is worth nothing to anyone else.
    verifier, challenge = oauth.pkce()

    def url_for(redirect: str) -> str:
        from urllib.parse import urlencode

        asked = {
            row.callback_param: redirect,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{row.authorize_url}?{urlencode(asked)}"

    # 2. The browser, and the redirect it comes back on.
    answer = await oauth.grant(url_for, say)
    code = answer.get("code")
    if not code:
        raise ConfigError(f"{name}: sign-in was refused", hint=answer.get("error", ""))
    # 3. The exchange: the code and the verifier for the key itself.
    sent = {"code": code, "code_verifier": verifier, "code_challenge_method": "S256"}
    issued = await oauth.post(row.exchange_url, sent, send=row.send)
    key = issued.get(row.field) if isinstance(issued, dict) else None
    if not isinstance(key, str) or not key:
        raise ConfigError(f"{name}: no key came back", hint=f"it answered {list(issued)}")
    keep(name, key, say)
    return key


def keep(name: str, key: str, say: Callable[[str], None]) -> None:
    """The keyring if there is one; otherwise the key once, on screen, and nowhere else."""
    if store.available():
        store.write(account(name), key)
        say(f"signed in to {name}; the key is in your keyring")
        return
    say(f"signed in to {name}. There is no keyring here, so edgar kept nothing.")
    say(f"{store.MISSING}\n\nor use this key yourself, once:\n\n{key}\n")
