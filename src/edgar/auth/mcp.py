"""Signing in to a remote MCP server: OAuth 2.1 with PKCE, discovered from what
the server publishes [TOOL-7, ADR-0032, ADR-0047].

A remote server that wants a token answers 401 and names its protected-resource
metadata; that names its authorization server, which names its endpoints and,
usually, where a client like edgar can register itself. `edgar mcp login NAME`
walks that chain once; after it, the token is in the keyring and the transport
sends it.
"""

# sign_in(url, say)  1. ask the resource what authorizes it
#                    2. ask that server where to send people and codes
#                    3. register edgar as a client, if it takes registrations
#                    4. the browser, the code, the token; keep it
# token(url)         the stored access token, refreshed if it has expired
# forget(url)        drop what is stored for this server
#
# Only `edgar mcp login` signs in: a turn never opens a browser by itself. A call
# to a server with no token fails with the command to run, like any tool failure.

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urljoin

from edgar.auth import oauth, store
from edgar.core.errors import ConfigError
from edgar.tools.custom import SECRETS

CLIENT = "edgar"
SCOPES = ""  # what the server grants by default; MCP servers publish their own


def account(url: str) -> str:
    return f"mcp:{url}"


def keep(url: str, holding: dict[str, Any]) -> None:
    store.write(account(url), json.dumps(_secret(holding)))


def kept(url: str) -> dict[str, Any]:
    said = store.read(account(url))
    return _secret(json.loads(said) if said else {})


def _secret(found: dict[str, Any]) -> dict[str, Any]:
    # A token is a secret like any key: whether it was just issued or read back, it
    # is redacted from everything edgar prints or records from here on [TOOL-6].
    for name in ("access_token", "refresh_token"):
        if isinstance(found.get(name), str):
            SECRETS.add(found[name])
    return found


def forget(url: str) -> bool:
    return store.erase(account(url))


async def token(url: str) -> str | None:
    """The token to send, refreshed if the stored one has run out."""
    found = kept(url)
    if not found:
        return None
    if found.get("expires_at", 0) > time.time() + 30:
        said = found.get("access_token")
        return said if isinstance(said, str) else None
    if not found.get("refresh_token"):
        return None
    asked = {
        "grant_type": "refresh_token",
        "refresh_token": found["refresh_token"],
        "client_id": found.get("client_id", CLIENT),
    }
    issued = await oauth.post(found["token_url"], asked)
    keep(url, _token(found, issued))
    return str(issued.get("access_token", "")) or None


async def sign_in(url: str, say: Callable[[str], None]) -> None:
    """The whole chain, once, for one server."""
    # 1. What authorizes this resource, and where its endpoints are.
    resource = await _metadata(url)
    where = resource.get("authorization_servers") or []
    if not where:
        raise ConfigError(f"{url} publishes no authorization server", hint="ask whoever runs it")
    server = await _endpoints(str(where[0]))
    # 2. The address the browser will come back to, then who edgar is to this
    #    server: a client id it gave us before, or a registration naming that address.
    back = await oauth.listen()
    found = kept(url)
    client = found.get("client_id") or await _register(server, url, back.redirect)
    # 3. The browser, and the code it redirects back.
    verifier, challenge = oauth.pkce()
    scope = SCOPES or " ".join(resource.get("scopes_supported") or [])

    def url_for(redirect: str) -> str:
        asked = {
            "response_type": "code",
            "client_id": client,
            "redirect_uri": redirect,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": url,  # RFC 8707: the token is for this server only
        }
        if scope:
            asked["scope"] = scope
        return f"{server['authorization_endpoint']}?{urlencode(asked)}"

    answer = await oauth.visit(back, url_for(back.redirect), say)
    if "code" not in answer:
        raise ConfigError(f"{url}: sign-in was refused", hint=answer.get("error", ""))
    # 4. The token, and the keyring.
    sent = {
        "grant_type": "authorization_code",
        "code": answer["code"],
        "redirect_uri": answer.get("redirect_uri", ""),
        "client_id": client,
        "code_verifier": verifier,
        "resource": url,
    }
    issued = await oauth.post(str(server["token_endpoint"]), sent)
    kept_now = {"client_id": client, "token_url": str(server["token_endpoint"])}
    keep(url, _token(kept_now, issued))
    say(f"signed in to {url}; the token is in your keyring")


def _token(found: dict[str, Any], issued: dict[str, Any]) -> dict[str, Any]:
    # An expiry is kept as a moment, not a duration, so a later session can read it.
    lasts = float(issued.get("expires_in", 3600))
    new = {
        "access_token": str(issued.get("access_token", "")),
        "expires_at": time.time() + lasts,
        "refresh_token": issued.get("refresh_token") or found.get("refresh_token"),
    }
    return {**found, **{k: v for k, v in new.items() if v}}


async def _metadata(url: str) -> dict[str, Any]:
    return dict(await oauth.fetch(urljoin(url, "/.well-known/oauth-protected-resource")))


async def _endpoints(issuer: str) -> dict[str, Any]:
    for well_known in (
        ".well-known/oauth-authorization-server",
        ".well-known/openid-configuration",
    ):
        try:
            found = dict(await oauth.fetch(urljoin(issuer.rstrip("/") + "/", well_known)))
        except (ConnectionError, ValueError):
            continue
        if "authorization_endpoint" in found and "token_endpoint" in found:
            return found
    raise ConfigError(f"{issuer} publishes no OAuth metadata", hint="ask whoever runs it")


async def _register(server: dict[str, Any], url: str, redirect: str) -> str:
    # Dynamic client registration (RFC 7591): edgar has no client id anywhere, so a
    # server that takes registrations gives it one, and it is kept with the token.
    where = server.get("registration_endpoint")
    if not where:
        raise ConfigError(
            f"{url} needs a client id and its server registers none",
            hint="ask whoever runs it for one, and put it in headers instead",
        )
    asked = {
        "client_name": CLIENT,
        "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    issued = await oauth.post(str(where), asked, send="json")
    client = issued.get("client_id")
    if not isinstance(client, str):
        raise ConfigError(f"{url}: registration gave no client id", hint=str(issued)[:200])
    return client
