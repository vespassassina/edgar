"""Signing in from a terminal: authorization code with PKCE and a loopback
redirect (RFC 8252, RFC 7636) [ADR-0032].

The same three steps serve a provider that issues an API key this way and a remote
MCP server that issues an access token: make a verifier, send the human to a URL
that edgar prints first, and catch the redirect on 127.0.0.1.
"""

# pkce()      a random verifier and its S256 challenge
# listen()    open 127.0.0.1 on a port the OS picks, before the URL is built
# visit()     print the host, open the browser, wait for the redirect
# grant()     both of those, for a flow that needs nothing in between
# post()      a form POST that expects JSON back: the token or key exchange
#
# Nothing here knows which provider it is signing into: the caller builds the URL
# and reads the answer, so a new one is a table row, never a branch [PRV-3].

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

WAIT = 300.0  # five minutes to approve in the browser, then the flow gives up
PAGE = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
    "Connection: close\r\n\r\n<html><body><p>{said}</p>"
    "<p>You can close this tab and go back to the terminal.</p></body></html>"
)


def pkce() -> tuple[str, str]:
    """A verifier only this process knows, and the challenge the server sees."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass
class Loopback:
    """The port the browser will come back to, held open while the human approves."""

    redirect: str
    server: asyncio.Server
    answered: asyncio.Future[dict[str, str]]


async def listen() -> Loopback:
    # A port the OS picks, so nothing is reserved and two logins can overlap. It is
    # opened before the URL is built, because a server registering edgar as a client
    # is told this exact address (RFC 8252).
    answered: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
    server = await asyncio.start_server(_caught(answered), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return Loopback(f"http://127.0.0.1:{port}/callback", server, answered)


async def visit(
    back: Loopback, url: str, say: Callable[[str], None], wait: float = WAIT
) -> dict[str, str]:
    """Open the browser at `url` and wait for the redirect it comes back on."""
    # The host is named before anything opens: no hidden hosts [PRV-15].
    say(f"opening {urlparse(url).netloc} in your browser to sign in")
    say(f"if it does not open, go to:\n{url}")
    async with back.server:
        await asyncio.to_thread(webbrowser.open, url)
        try:
            # The redirect travels with the answer: the token request must repeat it.
            return {"redirect_uri": back.redirect, **await asyncio.wait_for(back.answered, wait)}
        except TimeoutError:
            raise ConnectionError("nobody approved the sign-in within five minutes") from None


async def grant(
    url_for: Callable[[str], str], say: Callable[[str], None], wait: float = WAIT
) -> dict[str, str]:
    """Listen, send the human to the browser, and return what came back."""
    back = await listen()
    return await visit(back, url_for(back.redirect), say, wait)


def _caught(
    answered: asyncio.Future[dict[str, str]],
) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], Any]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # The browser's first line is "GET /callback?code=… HTTP/1.1": that is all
        # that is wanted, and the rest of the request is drained and dropped.
        line = (await reader.readline()).decode("utf-8", "replace")
        query = parse_qs(urlparse(line.split(" ")[1] if " " in line else "").query)
        found = {key: value[0] for key, value in query.items()}
        said = "Signed in." if "code" in found else f"Sign-in failed: {found.get('error', '?')}"
        writer.write(PAGE.format(said=said).encode("utf-8"))
        await writer.drain()
        writer.close()
        if not answered.done():
            answered.set_result(found)

    return handle


async def post(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
    send: str = "form",
) -> Any:
    """One POST, JSON back: the token exchange, or a client registering itself.
    OAuth says form-encoded; some providers' own key exchange takes JSON."""
    import httpx  # only a sign-in pays for it (NFR-1)

    shaped: dict[str, Any] = {"json": body} if send == "json" else {"data": body}
    async with httpx.AsyncClient(timeout=30.0) as client:
        answer = await client.post(url, headers=headers or {}, **shaped)
    if answer.status_code >= 400:
        raise ConnectionError(f"HTTP {answer.status_code} from {urlparse(url).netloc}")
    return answer.json()


async def fetch(url: str) -> Any:
    """One GET that expects JSON: the metadata documents a server publishes."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        answer = await client.get(url, headers={"Accept": "application/json"})
    if answer.status_code >= 400:
        raise ConnectionError(f"HTTP {answer.status_code} from {url}")
    return answer.json()
