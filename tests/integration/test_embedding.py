"""`edgar.run()`, the embedding API [EXT-9, ADR-0051]."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from harness import tool_use
from scripted import ScriptedProvider, ScriptedResponse

import edgar
from edgar.config.load import load
from edgar.core.errors import ConfigError
from edgar.permissions.guard import Answer
from edgar.providers import fake


def test_run_completes_a_turn_like_the_cli_does(tmp_project: Path, home: Path) -> None:
    result = asyncio.run(
        edgar.run("read a.txt", cwd=tmp_project, mode="read-only", model="fake/test", home=home)
    )
    assert result.reason == "completed" and "hello" in result.text


def test_run_needs_an_explicit_mode(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="explicit mode"):
        asyncio.run(edgar.run("hi", cwd=tmp_project, model="fake/test", home=home, mode=None))


def test_run_answers_permission_prompts_through_its_own_asker(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    async def asker(tool: str, subject: str, reason: str) -> Answer:
        asked.append(tool)
        return "once"

    steps = [
        ScriptedResponse(tool_calls=[tool_use("write", {"path": "b.txt", "content": "x"})]),
        ScriptedResponse(text="done"),
    ]
    monkeypatch.setattr(fake, "make", lambda: ScriptedProvider(steps))
    result = asyncio.run(
        edgar.run(
            "write b.txt",
            cwd=tmp_project,
            mode="ask",
            model="fake/test",
            home=home,
            asker=asker,
        )
    )
    assert result.reason == "completed" and asked == ["write"]  # the caller's own asker answered


def test_run_accepts_an_already_loaded_config(tmp_project: Path, home: Path) -> None:
    config = load(tmp_project, home=home, env={}, flags={"model.default": ("fake/test", "test")})
    result = asyncio.run(edgar.run("read a.txt", cwd=tmp_project, config=config, mode="read-only"))
    assert "hello" in result.text
