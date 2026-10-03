"""`edgar keys`: keys for models and search live in the keyring, read after the environment
[CFG-6, ADR-0076]."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from edgar.auth import store
from edgar.cli import keys
from edgar.core.errors import UsageError
from edgar.core.events import EventBus
from edgar.tools.base import ToolContext
from edgar.tools.custom import SECRETS, expand


class Ring:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.items.get((service, account))

    def set_password(self, service: str, account: str, secret: str) -> None:
        self.items[(service, account)] = secret

    def delete_password(self, service: str, account: str) -> None:
        del self.items[(service, account)]


@pytest.fixture
def ring(monkeypatch: pytest.MonkeyPatch) -> Ring:
    ring = Ring()
    monkeypatch.setattr(store, "_keyring", lambda: ring)
    for var in ("OPENAI_API_KEY", "BRAVE_SEARCH_API_KEY", "MY_KEY"):
        monkeypatch.delenv(var, raising=False)
    return ring


def piped(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_a_search_provider_name_keeps_its_key_under_its_variable(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    piped(monkeypatch, "sekret-9\n")
    assert keys.command(["set", "search:brave"], tmp_path) == 0
    assert ring.items == {("edgar", "env:BRAVE_SEARCH_API_KEY"): "sekret-9"}
    assert "sekret-9" not in capsys.readouterr().out


def test_a_model_provider_name_and_a_raw_variable_both_work(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    piped(monkeypatch, "k1\n")
    keys.command(["set", "openai"], tmp_path)
    piped(monkeypatch, "k2\n")
    keys.command(["set", "MY_KEY"], tmp_path)
    assert {a for _, a in ring.items} == {"env:OPENAI_API_KEY", "env:MY_KEY"}


def test_nonsense_names_and_empty_keys_keep_nothing(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(UsageError):
        keys.command(["set", "not a name"], tmp_path)
    piped(monkeypatch, "\n")
    assert keys.command(["set", "openai"], tmp_path) == 1 and not ring.items


def test_the_list_shows_where_each_key_is_and_never_the_key(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ring.items[("edgar", "env:BRAVE_SEARCH_API_KEY")] = "sekret-9"
    monkeypatch.setenv("OPENAI_API_KEY", "sekret-env")
    keys.command([], tmp_path)
    out = capsys.readouterr().out
    rows = {line.split()[0]: line for line in out.splitlines() if "_" in line}
    assert "environment" in rows["openai"] and "keyring" in rows["search:brave"]
    assert "sekret" not in out and "groq" in out


def test_remove_forgets_it(ring: Ring, tmp_path: Path) -> None:
    ring.items[("edgar", "env:MY_KEY")] = "x"
    keys.command(["remove", "MY_KEY"], tmp_path)
    assert not ring.items


def test_the_environment_wins_and_the_keyring_fills_the_gap(
    ring: Ring, monkeypatch: pytest.MonkeyPatch
) -> None:
    ring.items[("edgar", "env:MY_KEY")] = "from-ring"
    assert expand("Bearer ${env:MY_KEY}") == "Bearer from-ring" and "from-ring" in SECRETS
    monkeypatch.setenv("MY_KEY", "from-env")
    assert expand("${env:MY_KEY}") == "from-env"
    assert store.secret("MY_KEY", {}) is None  # a caller's own mapping never reaches the keyring


def test_a_provider_finds_its_key_in_the_keyring(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from edgar.providers.quirks import connect, quirks_for

    ring.items[("edgar", "env:OPENAI_API_KEY")] = "k-ring"
    _, key = connect("openai", quirks_for("openai", None), __import__("os").environ)
    assert key == "k-ring"


def test_a_search_tool_runs_on_a_keyring_key(
    ring: Ring, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import httpx

    from edgar.cli.init import TEMPLATES
    from edgar.tools.custom import load

    folder = tmp_path / "tools"
    folder.mkdir()
    (folder / "web_search.toml").write_text(
        (TEMPLATES / "tools" / "search" / "brave.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ring.items[("edgar", "env:BRAVE_SEARCH_API_KEY")] = "k-ring"
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handle)})
    )
    (tool,) = load([(folder, "project")])
    ctx = ToolContext(cwd=tmp_path, bus=EventBus(), blob_dir=tmp_path, max_output_tokens=8000)
    result = asyncio.run(tool.run({"query": "x"}, ctx))
    assert result.error is None and any(b"k-ring" in v for _, v in seen[0].headers.raw)
