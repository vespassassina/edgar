"""`edgar init`'s questions and the vendor list in the model picker [CFG-4, ADR-0034]."""

from __future__ import annotations

import asyncio
import json
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from edgar.cli import init
from edgar.cli.models import catalog, pick
from edgar.config.load import load
from edgar.core.events import EventBus


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


class _Many:
    def __init__(self, n: int) -> None:
        self._n = n

    async def models(self) -> list[str]:
        return [f"m{i}" for i in range(self._n)]


def _pick_from(
    monkeypatch: object, name: str, n: int, tmp: Path, *answers: str
) -> tuple[str | None, str]:
    from edgar.cli import models

    monkeypatch.setattr(models, "resolve", lambda *a, **k: (_Many(n), "-"))  # type: ignore[attr-defined]
    monkeypatch.setattr(models, "_offer_sign_in", _keep_env)  # type: ignore[attr-defined]
    said: list[str] = []
    config = load(tmp, home=tmp / "home", env={})
    got = asyncio.run(pick(config, {}, scripted(name, *answers), said.append))  # type: ignore[arg-type]
    return got, "\n".join(said)


async def _keep_env(name: str, config: object, env: object, ask: object, say: object) -> object:
    return env


def test_copilot_shows_its_whole_model_list(monkeypatch: object, tmp_path: Path) -> None:
    got, said = _pick_from(monkeypatch, "github-copilot", 75, tmp_path, "75")
    assert "75. m74" in said and "more; type a name" not in said
    assert got == "github-copilot/m74"


def test_every_provider_shows_its_whole_model_list(monkeypatch: object, tmp_path: Path) -> None:
    got, said = _pick_from(monkeypatch, "openrouter", 300, tmp_path, "300")
    assert "300. m299" in said and "more; type a name" not in said
    assert got == "openrouter/m299"


def test_the_provider_list_lines_up_on_the_longest_name(tmp_path: Path) -> None:
    config = load(tmp_path, home=tmp_path / "home", env={})
    said: list[str] = []
    asyncio.run(pick(config, {}, scripted(""), said.append))  # type: ignore[arg-type]
    rows = said[0].splitlines()
    starts = {row.index("http") for row in rows if "http" in row}
    assert len(starts) == 1, starts


def test_a_startup_pick_is_saved_for_every_project(monkeypatch: object, tmp_path: Path) -> None:
    from edgar.cli import models

    async def pick_one(*a: object, **k: object) -> str:
        return "openai/gpt-5"

    monkeypatch.setattr(models, "pick", pick_one)  # type: ignore[attr-defined]
    home = tmp_path / "home"
    (home / ".edgar").mkdir(parents=True)
    # An unedited init template: default is still the placeholder.
    (home / ".edgar" / "config.toml").write_text('[model]\n# default = "provider/model"\n')
    config = load(tmp_path, home=home, env={})
    asyncio.run(init.run(tmp_path, config, scripted(), lambda _: None, home))  # type: ignore[arg-type]
    saved = tomllib.loads((home / ".edgar" / "config.toml").read_text())
    assert saved["model"]["default"] == "openai/gpt-5"
    # Next directory: the default is found, so nothing would ask.
    assert load(tmp_path / "other", home=home, env={}).model.default == "openai/gpt-5"


def test_an_edited_user_config_is_never_rewritten(tmp_path: Path) -> None:
    from edgar.cli.models import remember

    path = tmp_path / "config.toml"
    path.write_text("[budget]\ndaily_cost_cap = 3.0\n")
    said = remember("openai/gpt-5", path)
    assert path.read_text() == "[budget]\ndaily_cost_cap = 3.0\n"
    assert "left alone" in said and 'default = "openai/gpt-5"' in said


def _tools_in(tmp: Path) -> list[str]:
    folder = tmp / ".edgar" / "tools"
    return sorted(p.stem for p in folder.glob("*.toml")) if folder.is_dir() else []


def test_enter_gives_the_agent_git_and_not_web_search(tmp_path: Path) -> None:
    _, said = run(tmp_path)
    assert _tools_in(tmp_path) == ["git-commit", "git-diff", "git-log", "git-status"]
    assert "edgar trust" in said


def test_naming_a_search_provider_copies_it_as_web_search_and_names_its_key(
    tmp_path: Path,
) -> None:
    # provider, four settings, then git, then the search provider
    _, said = run(tmp_path, "", "", "", "", "", "n", "Exa")
    assert _tools_in(tmp_path) == ["web_search"]
    assert "EXA_API_KEY" in said and "api.exa.ai" in (
        tmp_path / ".edgar" / "tools" / "web_search.toml"
    ).read_text(encoding="utf-8")


def test_an_unknown_search_provider_writes_nothing_and_an_existing_one_is_not_asked(
    tmp_path: Path,
) -> None:
    run(tmp_path, "", "", "", "", "", "n", "bing")
    assert _tools_in(tmp_path) == []
    folder = tmp_path / ".edgar" / "tools"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "web_search.toml").write_text("mine", encoding="utf-8")
    run(tmp_path, "", "", "", "", "", "n", "brave")
    assert (folder / "web_search.toml").read_text(encoding="utf-8") == "mine"


@pytest.mark.parametrize(
    "name", sorted(p.name for p in (init.TEMPLATES / "tools" / "search").iterdir())
)
def test_every_search_provider_sends_a_request_its_api_can_read(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import httpx

    from edgar.tools.base import ToolContext
    from edgar.tools.custom import load

    provider = name.removesuffix(".toml")
    key = tomllib.loads((init.TEMPLATES / "wizard.toml").read_text("utf-8"))["search"]["providers"][
        provider
    ]
    folder = tmp_path / "tools"
    folder.mkdir()
    (folder / "web_search.toml").write_text(
        (init.TEMPLATES / "tools" / "search" / name).read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv(key, "sekret-1")
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="results")

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handle)})
    )
    (tool,) = load([(folder, "project")])
    ctx = ToolContext(cwd=tmp_path, bus=EventBus(), blob_dir=tmp_path, max_output_tokens=8000)
    result = asyncio.run(tool.run({"query": 'say "hi" & more'}, ctx))
    (request,) = seen
    assert result.error is None and tool.schema.read_only
    assert any(b"sekret-1" in v for _, v in request.headers.raw) and "sekret-1" not in result.text
    if request.method == "POST":  # a JSON object carrying the query, not a JSON string
        body = json.loads(request.content)
        assert isinstance(body, dict) and 'say "hi" & more' in body.values()
    else:
        assert request.url.params.get("q") == 'say "hi" & more'


def test_an_existing_tool_file_is_never_overwritten_or_asked_about_again(tmp_path: Path) -> None:
    folder = tmp_path / ".edgar" / "tools"
    folder.mkdir(parents=True)
    mine = 'name = "git-status"\n'
    (folder / "git-status.toml").write_text(mine, encoding="utf-8")
    run(tmp_path)
    assert (folder / "git-status.toml").read_text(encoding="utf-8") == mine
    assert (folder / "git-log.toml").exists()


def test_nothing_is_written_when_nobody_can_answer(tmp_path: Path) -> None:
    config = load(tmp_path, home=tmp_path / "home", env={})
    asyncio.run(init.run(tmp_path, config, None, lambda _: None))
    assert _tools_in(tmp_path) == []


def test_the_shipped_tool_templates_match_the_examples() -> None:
    root = Path(__file__).resolve().parents[2]
    for f in (init.TEMPLATES / "tools").glob("**/*.toml"):
        mine = f.relative_to(init.TEMPLATES / "tools")
        assert f.read_text(encoding="utf-8") == (root / "examples" / "tools" / mine).read_text(
            encoding="utf-8"
        )
