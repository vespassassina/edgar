"""Signing in without a key: a command the user names prints a short-lived token,
the way Azure, Google Cloud and AWS hand one out [PRV-20, CFG-6]."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from cassettes import Replay
from harness import Recorder
from wire import Reply, ok, openai_sse

from edgar.config.load import load
from edgar.config.schema import Config, ProviderSection
from edgar.core.errors import ConfigError
from edgar.core.events import EventBus
from edgar.core.message import Message, TextBlock
from edgar.providers import quirks
from edgar.providers.registry import resolve

TOKEN = "tok-9f2c"  # what the fake cloud CLI prints
AZURE = "https://r.openai.azure.com"


def mint(tmp_path: Path, *, fail: bool = False) -> list[str]:
    """A cross-platform stand-in for `gcloud auth print-access-token`: it counts
    its runs in a file, then prints the token, or fails the way a lapsed sign-in does.
    The token is split in the argv, so a leak found later is the token's, not the argv's."""
    script = (
        f"import pathlib, sys; p = pathlib.Path({str(tmp_path / 'runs')!r}); "
        "p.write_text(str(int(p.read_text() or 0) + 1) if p.exists() else '1'); "
        + (
            "sys.exit('ERROR: please run gcloud auth login')"
            if fail
            else f"print({TOKEN[:4]!r} + {TOKEN[4:]!r})"
        )
    )
    return [sys.executable, "-c", script]


def runs(tmp_path: Path) -> int:
    counter = tmp_path / "runs"
    return int(counter.read_text()) if counter.exists() else 0


def ask(model: str, block: ProviderSection, env: dict[str, str], turns: int = 1) -> Replay:
    """Resolve `model` with one [providers.NAME] block and run `turns` requests."""
    transport = Replay([ok(openai_sse(Reply(text="hi"))) for _ in range(turns)])
    config = Config(providers={model.split("/")[0]: block})
    provider, name = resolve(model, config, env=env, transport=transport)
    messages = [Message("system", (TextBlock("sys"),)), Message.user("hi")]
    for _ in range(turns):
        asyncio.run(provider.stream(messages, [], model=name, bus=EventBus()))
    return transport


def test_the_commands_token_is_sent_as_bearer(tmp_path: Path) -> None:
    block = ProviderSection(
        kind="openai-compatible", base_url="https://cloud.test/v1", api_key_command=mint(tmp_path)
    )
    transport = ask("vertex/google/gemini-2.5-flash", block, env={})
    assert transport.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert transport.requests[0].body["model"] == "google/gemini-2.5-flash"


def test_azure_switches_from_its_key_header_to_a_bearer_token(tmp_path: Path) -> None:
    # Entra ID sign-in: no AZURE_OPENAI_API_KEY at all, and no api-key header [PRV-20].
    transport = ask(
        "azure/dep",
        ProviderSection(api_key_command=mint(tmp_path)),
        {"AZURE_OPENAI_ENDPOINT": AZURE},
    )
    (request,) = transport.requests
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert "api-key" not in request.headers


def test_a_key_in_the_environment_wins_and_the_command_never_runs(tmp_path: Path) -> None:
    env = {"AZURE_OPENAI_API_KEY": "k", "AZURE_OPENAI_ENDPOINT": AZURE}
    transport = ask("azure/dep", ProviderSection(api_key_command=mint(tmp_path)), env)
    assert transport.requests[0].headers["api-key"] == "k"
    assert runs(tmp_path) == 0


def test_the_token_is_reused_for_ten_minutes_then_minted_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("edgar.providers.quirks.time.monotonic", lambda: clock[0])
    token = quirks.Minted(mint(tmp_path))
    assert token.token() == TOKEN and runs(tmp_path) == 1
    clock[0] += 599
    assert token.token() == TOKEN and runs(tmp_path) == 1
    clock[0] += 2
    assert token.token() == TOKEN and runs(tmp_path) == 2


def test_a_lapsed_sign_in_stops_before_any_request_and_says_how_to_sign_in(
    tmp_path: Path,
) -> None:
    block = ProviderSection(api_key_command=mint(tmp_path, fail=True))
    with pytest.raises(ConfigError) as caught:
        ask("azure/dep", block, {"AZURE_OPENAI_ENDPOINT": AZURE})
    assert "please run gcloud auth login" in str(caught.value)
    assert "az login" in (caught.value.hint or "")


def test_a_missing_command_is_a_config_error_not_a_crash() -> None:
    with pytest.raises(ConfigError, match="no-such-cloud-cli"):
        quirks.Minted(["no-such-cloud-cli", "token"]).token()


def test_the_command_is_read_from_user_config_only(tmp_project: Path, home: Path) -> None:
    # A cloned repository must not choose the program that mints your credential.
    line = '[providers.azure]\napi_key_command = ["az", "account", "get-access-token"]\n'
    (home / ".edgar").mkdir()
    (home / ".edgar" / "config.toml").write_text(line, encoding="utf-8")
    assert load(tmp_project, home=home, env={}).providers["azure"].api_key_command == [
        "az",
        "account",
        "get-access-token",
    ]
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text(line, encoding="utf-8")
    with pytest.raises(ConfigError, match="user config only"):
        load(tmp_project, home=home, env={})


def test_the_token_never_shows_in_a_repr_or_an_event(tmp_path: Path) -> None:
    token = quirks.Minted(mint(tmp_path))
    token.token()
    assert TOKEN not in repr(token)
    recorder, bus = Recorder(), EventBus()
    bus.subscribe(recorder)
    block = ProviderSection(api_key_command=mint(tmp_path))
    transport = Replay([ok(openai_sse(Reply(text="hi")))])
    provider, name = resolve(
        "azure/dep",
        Config(providers={"azure": block}),
        env={"AZURE_OPENAI_ENDPOINT": AZURE},
        transport=transport,
    )
    messages = [Message("system", (TextBlock("sys"),)), Message.user("hi")]
    asyncio.run(provider.stream(messages, [], model=name, bus=bus))
    assert recorder.names and TOKEN not in repr(recorder.events)
