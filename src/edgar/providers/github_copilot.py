"""GitHub Copilot: the one built-in provider outside the non-removable budget,
because it earns its keep with RFC 8628's device flow, the one exception to
"edgar never signs in with anyone's subscription" [PRV-19, ADR-0043, ADR-0069].

Stripped from a build (v3/v4 deleted [NFR-12]): `github-copilot` still names the
openai-compatible adapter in `registry.BUILTIN`, but `quirks.py`'s lazy lookup
finds no row here and falls through to its "needs base_url" error, so a leaner
copy of edgar degrades to an honest message instead of a broken one.
"""

# ROW        the vendor's row: headers it requires, context size, its device flow
# sign_in()  edgar login github-copilot: read the client id, then poll for a token
# _poll()    RFC 8628: a code typed in on another screen, polled until approved

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass

from edgar.auth.keys import keep
from edgar.auth.oauth import post
from edgar.core.errors import ConfigError
from edgar.providers.quirks import Quirks

_ACCEPT = {"Accept": "application/json"}
_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass(frozen=True, slots=True)
class Device:
    """A subscription's device flow (RFC 8628), the one exception to ADR-0032's
    "never a subscription" rule, granted only where the vendor documents it
    [PRV-19, ADR-0043]. client_id_env names the variable holding edgar's own
    registered app id: not a secret, but there is no working default to ship,
    since only the maintainer can register it on their own GitHub account."""

    device_url: str
    token_url: str
    client_id_env: str
    scope: str = ""


ROW = Quirks(
    "https://api.githubcopilot.com",
    "GITHUB_COPILOT_API_KEY",
    images=True,
    parallel_tools=True,
    max_context=128_000,
    max_output=16_384,
    extra_headers={"Copilot-Integration-Id": "vscode-chat", "Editor-Version": "edgar/4.0"},
    device=Device(
        "https://github.com/login/device/code",
        "https://github.com/login/oauth/access_token",
        "GITHUB_COPILOT_CLIENT_ID",
    ),
)


def sign_in(name: str, row: Device, say: Callable[[str], None]) -> None:
    """`edgar login github-copilot`: edgar's own OAuth app id must already be in
    the environment [CFG-6]; only the maintainer can register one, so there is
    no working default to ship."""
    client_id = os.environ.get(row.client_id_env)
    if not client_id:
        raise ConfigError(
            f"{name}: {row.client_id_env} is not set",
            hint="register edgar's own OAuth app on github.com/settings/developers, "
            f"then export {row.client_id_env}=…",
        )
    asyncio.run(_poll(name, row, client_id, say))


async def _poll(name: str, row: Device, client_id: str, say: Callable[[str], None]) -> None:
    # 1. Ask for a code, and the URL where a human types it in elsewhere.
    offer = await post(row.device_url, {"client_id": client_id, "scope": row.scope}, _ACCEPT)
    say(f"go to {offer['verification_uri']} and enter code {offer['user_code']}")
    interval = float(offer.get("interval", 5))
    deadline = asyncio.get_event_loop().time() + float(offer.get("expires_in", 900))
    # 2. Poll: "authorization_pending" is normal, not a failure, until it isn't.
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(interval)
        body = await post(
            row.token_url,
            {"client_id": client_id, "device_code": offer["device_code"], "grant_type": _GRANT},
            _ACCEPT,
        )
        if "access_token" in body:
            keep(name, body["access_token"], say)
            return
        error = body.get("error")
        if error == "slow_down":
            interval += 5
        elif error != "authorization_pending":
            raise ConfigError(f"{name}: sign-in failed: {error}")
    raise ConfigError(f"{name}: nobody approved the sign-in within fifteen minutes")
