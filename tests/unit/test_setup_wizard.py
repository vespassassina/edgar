"""`edgar init`'s questions and the vendor list in the model picker [CFG-4, ADR-0034]."""

from __future__ import annotations

import asyncio
import tomllib
from collections.abc import Callable
from pathlib import Path

from edgar.cli import init
from edgar.cli.models import catalog, pick
from edgar.config.load import load


def scripted(*answers: str) -> Callable[[str], object]:
    queue = list(answers)

    async def ask(prompt: str) -> str:
        return queue.pop(0) if queue else ""

    return ask


def run(tmp: Path, *answers: str) -> tuple[str | None, str]:
    config = load(tmp, home=tmp / "home", env={})
    said: list[str] = []
    chosen = asyncio.run(init.run(tmp, config, scripted(*answers), said.append))  # type: ignore[arg-type]
    return chosen, "\n".join(said)


def test_the_catalog_names_the_common_vendors_with_a_host_and_a_key_variable() -> None:
    vendors = catalog()
    for name in ("groq", "mistral", "deepseek", "together", "xai", "gemini", "lmstudio"):
        assert name in vendors, name
    for name, row in vendors.items():
        assert row["base_url"].startswith("http"), name
        assert row.get("kind", "openai-compatible") in ("openai-compatible", "anthropic"), name


def test_the_picker_lists_catalog_vendors_beside_the_built_ins(tmp_path: Path) -> None:
    config = load(tmp_path, home=tmp_path / "home", env={})
    said: list[str] = []
    asyncio.run(pick(config, {}, scripted(""), said.append))  # type: ignore[arg-type]
    listed = said[0]
    assert "openai" in listed and "groq" in listed and "deepseek" in listed


def test_enter_through_every_question_keeps_the_defaults(tmp_path: Path) -> None:
    run(tmp_path, "", "", "", "", "")
    written = (tmp_path / ".edgar" / "config.toml").read_text(encoding="utf-8")
    assert not any(tomllib.loads(written).values())  # every key is still a comment


def test_answers_become_settings_in_the_written_config(tmp_path: Path) -> None:
    # Skip the provider question with Enter, then mode, verify, session cap, daily cap.
    run(tmp_path, "", "auto", "just test", "5", "20")
    written = tomllib.loads((tmp_path / ".edgar" / "config.toml").read_text(encoding="utf-8"))
    assert written["permissions"]["mode"] == "auto"
    assert written["verify"]["command"] == "just test"
    assert written["budget"] == {"session_cost_cap": 5.0, "daily_cost_cap": 20.0}


def test_yolo_and_nonsense_are_not_taken(tmp_path: Path) -> None:
    _, said = run(tmp_path, "", "yolo", "", "lots", "")
    written = tomllib.loads((tmp_path / ".edgar" / "config.toml").read_text(encoding="utf-8"))
    assert not written["permissions"] and not written["budget"]
    assert "not understood" in said


def test_a_catalog_vendor_writes_its_own_block(tmp_path: Path) -> None:
    chosen, _ = run(tmp_path, "groq", "llama-3.3-70b-versatile", "", "", "", "")
    assert chosen == "groq/llama-3.3-70b-versatile"
    written = tomllib.loads((tmp_path / ".edgar" / "config.toml").read_text(encoding="utf-8"))
    assert written["providers"]["groq"]["base_url"].startswith("https://")
    assert written["model"]["default"] == chosen
