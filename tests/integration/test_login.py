"""Signing in: `edgar login PROVIDER` and `edgar mcp login NAME` [PRV-18, TOOL-7,
CFG-6, ADR-0032].

No browser and no network: the "browser" is a loopback client the test drives, the
keyring is a dictionary, and every HTTP exchange is a function the test provides.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from netguard import allow, disallow

from edgar.auth import keys, oauth, store
from edgar.auth import mcp as mcp_auth
from edgar.cli.admin import command
from edgar.core.errors import ConfigError
from edgar.providers.quirks import QUIRKS, connect, quirks_for
from edgar.tools.custom import SECRETS, scrub
from edgar.tools.mcp.http import Http


class Ring:
    """A keyring in a dictionary, the shape `keyring` itself has."""

    def __init__(self) -> None:
        self.held: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.held.get((service, account))

    def set_password(self, service: str, account: str, secret: str) -> None:
        self.held[(service, account)] = secret

    def delete_password(self, service: str, account: str) -> None:
        del self.held[(service, account)]


@pytest.fixture
def ring(monkeypatch: pytest.MonkeyPatch) -> Ring:
    fake = Ring()
    monkeypatch.setattr(store, "_keyring", lambda: fake)
    return fake


def browser(answer: dict[str, str]) -> Any:
    """Stands in for the user's browser: it visits the redirect edgar is waiting on."""

    def opened(url: str) -> bool:
        from urllib.parse import parse_qs, urlparse

        asked = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        back = urlparse(asked.get("redirect_uri") or asked.get("callback_url", ""))
        allow(back.hostname or "", back.port or 0)
        query = "&".join(f"{k}={v}" for k, v in answer.items())
        request = f"GET {back.path}?{query} HTTP/1.1\r\nHost: x\r\n\r\n"
        with __import__("socket").create_connection((back.hostname, back.port)) as sock:
            sock.sendall(request.encode())
            sock.recv(4096)
        disallow(back.hostname or "", back.port or 0)
        opened.seen = url  # type: ignore[attr-defined]
        return True

    return opened


def test_the_challenge_is_the_verifier_hashed_the_way_the_server_will_check_it() -> None:
    verifier, challenge = oauth.pkce()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    assert challenge == base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert "=" not in challenge and len(verifier) > 42  # RFC 7636's minimum


def test_a_provider_login_exchanges_the_code_for_a_key_and_keeps_it(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[str] = []
    sent: dict[str, Any] = {}

    async def post(url: str, body: dict[str, Any], headers: Any = None, send: str = "form") -> Any:
        sent.update(body | {"url": url, "send": send})
        return {"key": "sk-or-secret"}

    monkeypatch.setattr(oauth, "post", post)
    monkeypatch.setattr("webbrowser.open", browser({"code": "the-code"}))
    row = QUIRKS["openrouter"].oauth
    assert row is not None
    key = asyncio.run(keys.login("openrouter", row, said.append))

    assert key == "sk-or-secret"
    assert ring.held[("edgar", "provider:openrouter")] == "sk-or-secret"
    # The code came back through the browser; the verifier never left this process.
    assert sent["code"] == "the-code" and sent["code_challenge_method"] == "S256"
    assert sent["url"] == "https://openrouter.ai/api/v1/auth/keys" and sent["send"] == "json"
    printed = "\n".join(said)
    assert "openrouter.ai" in printed  # the host is named before the browser opens
    assert "sk-or-secret" not in printed  # the key is not printed when it is kept
    assert scrub("here is sk-or-secret") == "here is [redacted]"  # [TOOL-6]


def test_without_a_keyring_the_key_is_printed_once_and_stored_nowhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store, "_keyring", lambda: None)
    said: list[str] = []
    keys.keep("openrouter", "sk-shown", said.append)
    printed = "\n".join(said)
    assert "sk-shown" in printed and "keyring" in printed  # [CFG-6]
    assert keys.stored("openrouter") is None


def test_a_key_from_the_keyring_is_used_and_logout_forgets_it(ring: Ring) -> None:
    ring.set_password("edgar", "provider:openrouter", "sk-kept")
    _, key = connect("openrouter", quirks_for("openrouter", None), {})
    assert key == "sk-kept"  # no OPENROUTER_API_KEY needed [CFG-6]
    assert keys.logout("openrouter") is True
    with pytest.raises(ConfigError) as raised:
        connect("openrouter", quirks_for("openrouter", None), {})
    assert "edgar login openrouter" in (raised.value.hint or "")


def test_models_list_says_whether_a_provider_is_signed_in(
    ring: Ring, capsys: Any, tmp_path: Path
) -> None:
    from edgar.cli.models import list_models

    list_models(tmp_path, env={})
    assert "edgar login openrouter" in capsys.readouterr().out
    ring.set_password("edgar", "provider:openrouter", "sk-kept")
    list_models(tmp_path, env={})
    assert "logged in" in capsys.readouterr().out


def test_the_picker_offers_to_sign_in_instead_of_bouncing_you_out(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`edgar models` with no key used to fail at the provider and send you away to
    run `edgar login` yourself; now Enter signs in and the picker carries on."""
    from edgar.cli.models import pick
    from edgar.config.schema import Config

    async def post(url: str, body: dict[str, Any], headers: Any = None, send: str = "form") -> Any:
        return {"key": "sk-or-fresh"}

    monkeypatch.setattr(oauth, "post", post)
    monkeypatch.setattr("webbrowser.open", browser({"code": "the-code"}))
    listed: list[str] = []

    async def models(self: Any) -> list[str]:
        listed.append(self.api_key)
        return ["z-ai/glm-5", "anthropic/claude-opus-5"]

    monkeypatch.setattr("edgar.providers.openai_compat.OpenAICompatible.models", models)
    answers, said = ["openrouter", "", "2"], list[str]()

    async def ask(question: str) -> str:
        said.append(question)
        return answers.pop(0)

    chosen = asyncio.run(pick(Config(), {}, ask, said.append))

    asked = [line for line in said if "Sign in now? [Y/n]" in line]
    assert len(asked) == 1 and said.index(asked[0]) < len(said) - 1  # asked, once, early
    assert chosen == "openrouter/anthropic/claude-opus-5"  # the picker never stopped
    assert listed == ["sk-or-fresh"]  # the key it just issued is the one it used
    assert ring.held[("edgar", "provider:openrouter")] == "sk-or-fresh"


def test_the_picker_still_takes_no_for_an_answer(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    from edgar.cli.models import pick
    from edgar.config.schema import Config

    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("no browser on 'n'"))
    answers, said = ["openrouter", "n"], list[str]()

    async def ask(question: str) -> str:
        return answers.pop(0)

    assert asyncio.run(pick(Config(), {}, ask, said.append)) is None
    assert "OPENROUTER_API_KEY" in said[-1]  # the old message, still there


# The remote MCP server's own sign-in [TOOL-7, ADR-0032]

RESOURCE = {"authorization_servers": ["https://auth.example.test"], "scopes_supported": ["read"]}
SERVER = {
    "authorization_endpoint": "https://auth.example.test/authorize",
    "token_endpoint": "https://auth.example.test/token",
    "registration_endpoint": "https://auth.example.test/register",
}


def discovery(monkeypatch: pytest.MonkeyPatch, posts: list[dict[str, Any]]) -> None:
    async def fetch(url: str) -> Any:
        if "oauth-protected-resource" in url:
            return RESOURCE
        if "oauth-authorization-server" in url:
            return SERVER
        raise ConnectionError(f"HTTP 404 from {url}")

    async def post(url: str, body: dict[str, Any], headers: Any = None, send: str = "form") -> Any:
        posts.append(body | {"url": url})
        if url.endswith("/register"):
            return {"client_id": "client-42"}
        return {"access_token": "tok-1", "refresh_token": "ref-1", "expires_in": 3600}

    monkeypatch.setattr(oauth, "fetch", fetch)
    monkeypatch.setattr(oauth, "post", post)


def test_signing_in_to_a_server_discovers_it_registers_and_keeps_the_token(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    posts: list[dict[str, Any]] = []
    discovery(monkeypatch, posts)
    monkeypatch.setattr("webbrowser.open", browser({"code": "mcp-code"}))
    said: list[str] = []
    asyncio.run(mcp_auth.sign_in("https://mcp.example.test/mcp", said.append))

    registered, exchanged = posts[0], posts[1]
    # The client registers the exact loopback address the browser will come back to.
    assert registered["redirect_uris"][0] == exchanged["redirect_uri"]
    assert registered["token_endpoint_auth_method"] == "none"  # a public client: PKCE only
    assert exchanged["client_id"] == "client-42" and exchanged["code"] == "mcp-code"
    assert exchanged["resource"] == "https://mcp.example.test/mcp"  # RFC 8707
    kept = json.loads(ring.held[("edgar", "mcp:https://mcp.example.test/mcp")])
    assert kept["access_token"] == "tok-1" and kept["expires_at"] > time.time()
    assert "tok-1" not in "\n".join(said) and scrub("tok-1") == "[redacted]"


def test_a_token_that_has_run_out_is_refreshed_before_it_is_sent(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://mcp.example.test/mcp"
    ring.set_password(
        "edgar",
        f"mcp:{url}",
        json.dumps(
            {
                "access_token": "old",
                "refresh_token": "ref-1",
                "expires_at": time.time() - 10,
                "token_url": "https://auth.example.test/token",
                "client_id": "client-42",
            }
        ),
    )
    posts: list[dict[str, Any]] = []
    discovery(monkeypatch, posts)
    assert asyncio.run(mcp_auth.token(url)) == "tok-1"
    assert posts[0]["grant_type"] == "refresh_token"
    assert json.loads(ring.held[("edgar", f"mcp:{url}")])["access_token"] == "tok-1"


def test_the_transport_sends_the_token_and_a_401_says_how_to_sign_in(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://mcp.example.test/mcp"
    ring.set_password(
        "edgar",
        f"mcp:{url}",
        json.dumps({"access_token": "tok-9", "expires_at": time.time() + 600}),
    )
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        if len(seen) == 1:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
        return httpx.Response(401, json={"error": "no"})

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(httpx, "AsyncClient", _client(transport))

    async def run() -> str:
        http = Http(url, {}, 30.0)
        await http.open()
        await http.request({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
        try:
            await http.request({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        except ConnectionError as exc:
            return str(exc)
        finally:
            await http.close()
        return ""

    said = asyncio.run(run())
    assert seen[0] == "Bearer tok-9"  # the stored token goes on every request
    assert "edgar mcp login" in said  # a turn never opens a browser [ADR-0047]


def _client(transport: httpx.MockTransport) -> Any:
    real = httpx.AsyncClient

    def make(**kwargs: Any) -> httpx.AsyncClient:
        return real(**{**kwargs, "transport": transport})

    return make


def test_mcp_login_needs_a_remote_server_and_logout_forgets_one(
    ring: Ring, tmp_project: Path, home: Path, capsys: Any
) -> None:
    (home / ".edgar").mkdir(parents=True, exist_ok=True)
    (home / ".edgar" / "config.toml").write_text(
        '[mcp.here]\ncommand = "python"\n[mcp.far]\nurl = "https://mcp.example.test/mcp"\n',
        encoding="utf-8",
    )
    ring.set_password("edgar", "mcp:https://mcp.example.test/mcp", json.dumps({"a": 1}))
    assert command(["mcp", "logout", "far"], tmp_project, home) == 0
    assert "signed out" in capsys.readouterr().out
    with pytest.raises(Exception) as raised:  # a local program needs no sign-in
        command(["mcp", "login", "here"], tmp_project, home)
    assert "local program" in str(raised.value)


def test_a_planted_token_never_appears_in_anything_edgar_prints(ring: Ring) -> None:
    ring.set_password(
        "edgar", "mcp:https://x.test/mcp", json.dumps({"access_token": "plant-me-42"})
    )
    mcp_auth.kept("https://x.test/mcp")
    assert "plant-me-42" in SECRETS
    assert scrub("the server said plant-me-42 back") == "the server said [redacted] back"
