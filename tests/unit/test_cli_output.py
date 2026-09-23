"""The printer, the status line and the model picker [CLI-5, CLI-15, CLI-23, CLI-30]."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fixture_server import FixtureServer

from edgar.cli.models import pick, remember
from edgar.cli.render import Printer, _notice, event_line
from edgar.cli.statusbar import Status
from edgar.config.schema import Config, ProviderSection
from edgar.core.events import (
    Escalation,
    Fallback,
    InputQueued,
    RequestFinished,
    RequestStarted,
    ToolStarted,
    TurnFinished,
    TurnStarted,
)
from edgar.providers.base import Usage


def printer(width: int = 30, color: bool = False) -> tuple[Printer, list[str]]:
    out: list[str] = []
    return Printer(out.append, color=color, width=lambda: width), out


def test_text_streams_whole_lines_wrapped_at_the_terminal_width() -> None:
    p, out = printer(width=21)
    for delta in ["The quick brown fox ", "jumps over the lazy dog.\nNext", " line"]:
        p.text(delta)
    assert out == ["The quick brown fox\n", "jumps over the lazy\n", "dog.\n"]
    p.end()
    assert out[-1] == "Next line\n"


def test_a_block_waits_for_the_end_of_the_line() -> None:
    p, out = printer()
    p.text("half a ")
    p.block("── btw ──")
    assert out == []  # never mid-line
    p.text("line\n")
    assert out == ["half a line\n", "── btw ──\n"]


def test_dim_text_uses_escapes_only_with_colour() -> None:  # [CLI-15]
    for color, expected in [(True, "\x1b[2mhmm\x1b[0m\n"), (False, "hmm\n")]:
        p, out = printer(color=color)
        p.text("hmm\n", dim=True)
        assert out == [expected]


def test_the_status_line_is_built_from_events() -> None:
    now = [100.0]
    status = Status("fake/test", clock=lambda: now[0])
    assert status.line() == "fake/test · 0.0k tok · $0.000"
    status(TurnStarted(turn_id="t", model="fake/test"))
    status(RequestStarted(provider="fake", model="fake/test", input_tokens=1200))
    status(ToolStarted(id="1", tool="read"))
    status(InputQueued(text="next", position=1))
    now[0] = 103.0
    line = status.line()
    assert line.endswith("read · 1 tool · 1.2k tok · $0.000 · 1 queued · 3s")
    status(RequestFinished(usage=Usage(1500, 100), cost=None, cached=0))
    status(TurnFinished(turn_id="t", usage=Usage(), cost=None, reason="completed"))
    assert status.line() == "fake/test · 1.6k tok · cost unknown · 1 queued"


def test_concurrent_subagents_get_their_own_row_until_they_finish() -> None:  # [SUB-9]
    now = [100.0]
    status = Status("fake/test", clock=lambda: now[0])
    status(TurnStarted(turn_id="t", model="fake/test"))
    assert status.rows() == [status.line()]  # nothing running below yet
    status(TurnStarted(turn_id="a", model="x", agent_id="helper-1", depth=1))
    status(TurnStarted(turn_id="b", model="x", agent_id="helper-2", depth=1))
    status(ToolStarted(id="1", tool="write", agent_id="helper-1", depth=1))
    rows = status.rows()
    assert len(rows) == 3  # the main row, plus one per subagent
    assert "helper-1: write" in rows[1] and "helper-2: thinking" in rows[2]
    status(
        TurnFinished(
            turn_id="a", usage=Usage(), cost=None, reason="completed", agent_id="helper-1", depth=1
        )
    )
    rows = status.rows()
    assert len(rows) == 2
    assert "helper-1" not in rows[1] and "helper-2" in rows[1]
    # A subagent's own events never touch the main row.
    assert status.line() == rows[0]


def test_fallback_and_escalation_are_never_silent() -> None:  # [ROUTE-10]
    fell_back = Fallback(from_model="a/one", to_model="b/two", reason="down")
    escalated = Escalation(from_model="a/one", to_model="b/two", reason="failed repeatedly")
    assert _notice(fell_back) == "a/one unreachable, falling back to b/two"
    assert _notice(escalated) == "escalating from a/one to b/two: failed repeatedly"


def test_the_status_line_shows_a_fallback_or_escalation_model() -> None:  # [ROUTE-10]
    status = Status("a/one")
    status(Fallback(from_model="a/one", to_model="b/two", reason="down"))
    assert status.model == "b/two"
    status(Escalation(from_model="b/two", to_model="c/three", reason="failed repeatedly"))
    assert status.model == "c/three"


def test_an_event_line_is_json_with_its_name() -> None:
    line = json.loads(event_line(RequestFinished(usage=Usage(3, 4), cost=0.5, cached=0)))
    assert line["event"] == "RequestFinished" and line["usage"]["output_tokens"] == 4


def test_the_picker_lists_the_chosen_providers_models_and_takes_a_number(tmp_path: Path) -> None:
    listing = {"object": "list", "data": [{"id": "qwen3:8b"}, {"id": "llama3.2"}]}
    exchange = {"status": 200, "headers": {"content-type": "application/json"}}
    with FixtureServer([exchange | {"body": json.dumps(listing)}]) as server:
        local = ProviderSection(kind="openai-compatible", base_url=server.base_url)
        config = Config(providers={"local": local})
        answers, said = ["local", "2"], list[str]()

        async def ask(question: str) -> str:
            return answers.pop(0)

        chosen = asyncio.run(pick(config, {}, ask, said.append))
    assert chosen == "local/qwen3:8b"  # sorted: llama3.2, qwen3:8b
    assert server.requests[0].url == "/v1/models"
    assert "local" in said[0] and "  2. qwen3:8b" in said[-1]


def test_the_picker_never_contacts_a_provider_you_did_not_pick() -> None:
    answers, said = [""], list[str]()

    async def ask(question: str) -> str:
        return answers.pop(0)

    assert asyncio.run(pick(Config(), {}, ask, said.append)) is None  # nothing was fetched


def test_a_missing_key_is_named_not_asked_for() -> None:
    answers, said = ["openai"], list[str]()

    async def ask(question: str) -> str:
        return answers.pop(0)

    assert asyncio.run(pick(Config(), {}, ask, said.append)) is None
    assert "OPENAI_API_KEY" in said[-1]


def test_the_default_is_written_only_to_a_new_file(tmp_path: Path) -> None:  # [ADR-0034]
    path = tmp_path / ".edgar" / "config.toml"
    assert remember("ollama/qwen3:8b", path) == f"wrote {path}"
    assert path.read_text(encoding="utf-8") == '[model]\ndefault = "ollama/qwen3:8b"\n'
    message = remember("openai/gpt-5", path)
    assert "left alone" in message and 'default = "openai/gpt-5"' in message
    assert "ollama/qwen3:8b" in path.read_text(encoding="utf-8")  # untouched
