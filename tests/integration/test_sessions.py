"""Long sessions and their record: M5's "done when" [CTX-3, CTX-8, CTX-12, CTX-14,
CTX-17, CLI-11, BUD-2, BUD-3, PERM-12].

A provider that reads a big file every turn fills a small window fast, so a
200-turn session compacts again and again; every request is checked for the
pairing invariant and for an unchanged prefix, and the record on disk must
replay to exactly the view the loop ended with.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from harness import Recorder, new_session, runtime

from edgar.cli.oneshot import run_prompt
from edgar.cli.setup import finish, setup
from edgar.config.schema import BudgetSection, Config, ContextSection, ModelSection
from edgar.core.errors import ContextOverflow
from edgar.core.events import Compacted, EventBus, TurnFinished
from edgar.core.loop import Runtime, run_turn
from edgar.core.message import Message, TextBlock, ToolUseBlock
from edgar.core.session import Session
from edgar.core.units import pairing_violations
from edgar.providers.base import ProviderResponse, Usage
from edgar.providers.fake import FakeProvider
from edgar.storage.transcript import find, replay, start


class Busy(FakeProvider):
    """Reads big.txt `reads` times a turn, then says done; writes a summary when the
    compactor asks. Each request costs `cost`."""

    def __init__(self, reads: int = 1, cost: float | None = 0.001, window: int = 6000) -> None:
        self.capabilities = replace(FakeProvider.capabilities, max_context=window, max_output=1000)
        self.reads, self.cost = reads, cost
        self.requests: list[list[Message] | str] = []  # "compacted" between requests
        self.summaries = 0

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[Any], **_: Any
    ) -> ProviderResponse:
        if "Blobs worth re-reading" in messages[0].text:  # the summarise prompt
            self.summaries += 1
            return self._answer(messages, (TextBlock(f"Goal: summary {self.summaries}"),))
        self.requests.append(list(messages))
        done = 0
        for m in reversed(messages):
            if m.role == "user" and not m.meta.get("via"):
                break
            done += len(m.tool_calls)
        if done < self.reads:
            call = ToolUseBlock(f"tu_{len(self.requests)}", "read", {"path": "big.txt"})
            return self._answer(messages, (call,))
        return self._answer(messages, (TextBlock("done"),))

    def _answer(self, messages: Sequence[Message], content: tuple[Any, ...]) -> ProviderResponse:
        usage = Usage(self.count_tokens(messages), 5, approximate=True)
        stop = "tool_use" if isinstance(content[0], ToolUseBlock) else "end_turn"
        return ProviderResponse(Message("assistant", content), usage, stop, cost=self.cost)


def rig(
    root: Path, provider: Busy, *, keep: int = 2, budget: BudgetSection | None = None
) -> tuple[Session, Runtime, Recorder]:
    (root / "big.txt").write_text("lorem ipsum " * 170, encoding="utf-8")  # ~500 tokens
    recorder = Recorder()
    rt = runtime(provider, recorder)  # type: ignore[arg-type]  # Busy is a Provider
    rt = replace(rt, context=ContextSection(keep_last_turns=keep), budget=budget or BudgetSection())
    rt.bus.subscribe(
        lambda e: provider.requests.append("compacted") if isinstance(e, Compacted) else None
    )
    session = start(new_session(root))
    assert session.log is not None
    rt.bus.subscribe(session.log.event)
    return session, rt, recorder


def test_a_200_turn_session_compacts_often_and_replays_exactly(tmp_project: Path) -> None:
    provider = Busy()
    session, rt, recorder = rig(tmp_project, provider)

    async def talk() -> None:
        for n in range(200):
            await run_turn(session, f"turn {n}", rt)

    asyncio.run(talk())
    compactions = recorder.of(Compacted)
    assert len(compactions) > 20
    assert sum(c.stages == "S1" for c in compactions) > len(compactions) / 2  # mostly free
    assert provider.summaries >= 1
    requests = [r for r in provider.requests if isinstance(r, list)]
    assert all(pairing_violations(r) == [] for r in requests)
    assert len({r[0].text for r in requests}) == 1
    # Between compactions each request only appends to the one before [CTX-17].
    previous: list[Message] | None = None
    for request in provider.requests:
        if request == "compacted":
            previous = None
            continue
        assert isinstance(request, list)
        if previous is not None:
            assert request[: len(previous)] == previous
        previous = request

    resumed, turns = replay(find(tmp_project, session.id))
    assert resumed.transcript == session.transcript  # [CTX-14]
    assert turns == 200 and resumed.title == "turn 0"
    assert resumed.cost == pytest.approx(session.cost)


def test_a_long_tool_calling_turn_compacts_inside_itself(tmp_project: Path) -> None:
    provider = Busy(reads=40)
    session, rt, recorder = rig(tmp_project, provider)
    result = asyncio.run(run_turn(session, "read it all", rt))
    assert result.reason == "completed"
    assert any("S3" in c.stages for c in recorder.of(Compacted))
    assert recorder.names.index("Compacted") < recorder.names.index("TurnFinished")
    requests = [r for r in provider.requests if isinstance(r, list)]
    assert all(pairing_violations(r) == [] for r in requests)
    assert replay(find(tmp_project, session.id))[0].transcript == session.transcript


def test_pinned_content_over_the_window_is_an_overflow_with_a_hint(tmp_project: Path) -> None:
    provider = Busy()
    session, rt, _ = rig(tmp_project, provider)
    rt = replace(rt, system_prompt="instructions " * 3000)
    with pytest.raises(ContextOverflow) as info:
        asyncio.run(run_turn(session, "hello", rt))
    assert "/compact" in (info.value.hint or "") and info.value.exit_code == 1
    assert session.transcript[-1].text == "hello"  # never dropped silently [CTX-12]


def test_compacting_twice_does_nothing_the_second_time(tmp_project: Path) -> None:
    """[CTX-8]"""
    from edgar.context.compact import compact

    provider = Busy()
    session, rt, _ = rig(tmp_project, provider)

    async def talk() -> None:
        for n in range(8):
            await run_turn(session, f"turn {n}", rt)
        await compact(session, rt, force=True)
        before = list(session.transcript)
        await compact(session, rt, force=True)
        assert session.transcript == before

    asyncio.run(talk())
    assert session.transcript[1].meta.get("via") == "summary"


@pytest.mark.parametrize(
    ("budget", "cost", "requests"),
    [
        (BudgetSection(turn_cost_cap=0.0025), 0.001, 3),
        (BudgetSection(session_cost_cap=0.0015), 0.001, 2),
        (BudgetSection(turn_cost_cap=1.0), None, 1),  # unknown spend counts as over [BUD-5]
    ],
)
def test_a_cost_cap_stops_the_turn_before_the_next_request(
    tmp_project: Path, budget: BudgetSection, cost: float | None, requests: int
) -> None:
    provider = Busy(reads=10, cost=cost)
    session, rt, recorder = rig(tmp_project, provider, budget=budget)
    result = asyncio.run(run_turn(session, "read a lot", rt))
    assert result.reason == "budget_exceeded"  # [BUD-3]
    assert len(provider.requests) == requests
    assert recorder.of(TurnFinished)[-1].reason == "budget_exceeded"
    assert pairing_violations(session.transcript) == []


def test_p_exits_6_when_a_cap_is_reached(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text("[budget]\nsession_cost_cap = 0.0\n")
    code = run_prompt("hi", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home)
    assert code == 6
    assert "cost cap" in capsys.readouterr().err


def test_p_resumes_the_latest_session(tmp_project: Path, home: Path) -> None:
    def run(prompt: str, resume: str | None) -> int:
        return run_prompt(
            prompt, cwd=tmp_project, model=None, mode="ask", env={}, home=home, resume=resume
        )

    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/test"\n')
    assert run("first", None) == 0
    assert run("second", "") == 0  # --continue
    session, turns = replay(find(tmp_project, ""))
    assert [m.text for m in session.transcript if m.role == "user"] == ["first", "second"]
    assert turns == 2 and session.title == "first"
    assert len(list((tmp_project / ".edgar" / "sessions").glob("*.jsonl"))) == 1
    assert (tmp_project / ".edgar" / "sessions" / ".gitignore").read_text() == "*\n"


def test_find_wants_a_unique_id(tmp_project: Path) -> None:
    from edgar.core.errors import UsageError

    for n in range(2):
        start(new_session(tmp_project)).record({"type": "title", "text": str(n)})
    with pytest.raises(UsageError, match="several match"):
        find(tmp_project, "0")
    with pytest.raises(UsageError, match="none found"):
        find(tmp_project, "ZZZ")
    with pytest.raises(UsageError):
        find(tmp_project, "../x")


def test_a_control_file_changed_during_a_session_warns_the_next_one(
    tmp_project: Path, home: Path
) -> None:
    config = Config(model=ModelSection(default="fake/test"))
    s = setup(tmp_project, config, home=home, env={})
    session = start(Session(cwd=tmp_project, model="fake/test", mode="ask"))
    (tmp_project / "AGENTS.md").write_text("be terse\n")  # e.g. a write the user allowed
    finish(s, session)
    again = setup(tmp_project, config, home=home, env={})
    assert any("AGENTS.md" in w and session.id in w for w in again.warnings)  # [PERM-12]


def test_the_prefix_holds_personality_and_instructions_at_both_scopes(
    tmp_project: Path, home: Path
) -> None:
    from edgar.cli.setup import runtime as build_runtime

    (home / ".edgar").mkdir()
    (home / ".edgar" / "personality.md").write_text("user tone")
    (home / ".edgar" / "AGENTS.md").write_text("user rules")
    (tmp_project / "AGENTS.md").write_text("project rules")
    config = Config(model=ModelSection(default="fake/test"))
    rt = build_runtime(setup(tmp_project, config, home=home, env={}), EventBus())
    prompt = rt.system_prompt
    assert prompt.index("user tone") < prompt.index("project rules") < prompt.index("user rules")
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "personality.md").write_text("project tone " * 600)
    s = setup(tmp_project, config, home=home, env={})
    prompt = build_runtime(s, EventBus()).system_prompt
    assert "project tone" in prompt and "user tone" not in prompt  # replaces [ADR-0030]
    assert any("personality.md" in w for w in s.warnings)  # over 500 tokens [CTX-19]


def test_sessions_list_show_and_rm(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[CLI-11]"""
    from edgar.cli import admin

    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/test"\n')
    assert run_prompt("read a.txt", cwd=tmp_project, model=None, mode="ask", env={}, home=home) == 0
    sid = find(tmp_project, "").stem
    capsys.readouterr()
    assert admin.command(["sessions", "list"], tmp_project, home) == 0
    assert sid in capsys.readouterr().out
    assert admin.command(["sessions", "show", sid[:10]], tmp_project, home) == 0
    assert "user: read a.txt" in capsys.readouterr().out
    assert admin.command(["sessions", "rm", sid], tmp_project, home) == 0
    assert not list((tmp_project / ".edgar" / "sessions").glob("*.jsonl"))
    assert admin.command(["sessions", "frob"], tmp_project, home) == 2


def test_resume_keeps_the_model_unless_a_flag_names_one(tmp_project: Path, home: Path) -> None:
    from edgar.cli.setup import begin, prepare

    root, config = prepare(tmp_project, model="fake/test", mode="ask", env={}, home=home)
    first = start(Session(cwd=root, model="fake/other", mode="ask"))
    first.record({"type": "title", "text": "old"})
    session, rt = begin(setup(root, config, home=home, env={}), EventBus(), "")
    assert session.id == first.id and rt.name == "fake/test"  # --model wins
    assert replay(find(root, first.id))[0].model == "fake/test"  # and is recorded
    (root / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/third"\n')
    root, config = prepare(tmp_project, model=None, mode="ask", env={}, home=home)
    session, rt = begin(setup(root, config, home=home, env={}), EventBus(), first.id)
    assert rt.name == "fake/test"  # the session's own, not the config's


def test_prompt_show_includes_the_personality(
    tmp_project: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """[CTX-19]"""
    from edgar.cli.main import main

    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "personality.md").write_text("dry wit")
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert main(["prompt", "show"]) == 0
    out, err = capsys.readouterr()
    assert out.startswith("You are running inside edgar") and out.endswith("dry wit")
    assert "personality.md" in err
