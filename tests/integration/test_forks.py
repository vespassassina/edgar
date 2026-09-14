"""Forks, /save and --load, /history, the daily cap and `edgar cost` (M7) [CLI-22,
CLI-25, BUD-2, BUD-3, BUD-6, MEM-15].

Sessions are written the way the loop writes them (messages, then a TurnFinished
event per turn), so the fork arithmetic is tested against real records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar.cli.admin import command
from edgar.cli.main import main
from edgar.cli.oneshot import run_prompt
from edgar.cli.setup import Setup, begin, daily, setup, spending
from edgar.config.schema import BudgetSection, Config, ModelSection
from edgar.core.errors import BudgetExceeded, UsageError
from edgar.core.events import EventBus, TurnFinished
from edgar.core.message import Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.session import Session
from edgar.providers.base import Usage
from edgar.storage.transcript import (
    adopt,
    chain,
    conversation,
    entries,
    find,
    fork,
    replay,
    save,
    sessions_dir,
    start,
)


def talk(root: Path, *turns: str) -> Session:
    """A recorded session with one user message, one answer and one turn end per turn."""
    session = start(Session(cwd=root, model="fake/test", mode="ask"))
    for n, text in enumerate(turns):
        for message in (
            Message("user", (TextBlock(text),)),
            Message("assistant", (TextBlock(f"re {text}"),)),
        ):
            session.append(message)  # recorded as it is appended
        session.record({"type": "event", "event": "TurnFinished", "turn": n, "cost": 0.001})
    return session


def texts(path: Path) -> list[str]:
    session, _ = replay(path)
    return [m.text for m in session.transcript if m.role == "user"]


def test_a_fork_starts_where_its_parent_was_and_leaves_it_alone(tmp_project: Path) -> None:
    parent = talk(tmp_project, "one", "two", "three")
    at_two = fork(tmp_project, f"{parent.id}@2")  # [CLI-22]
    assert texts(at_two) == ["one", "two"]
    assert len(entries(at_two)) == 2  # a head and a fork line: nothing copied
    latest = fork(tmp_project, parent.id[:12])
    assert texts(latest) == ["one", "two", "three"]
    assert texts(fork(tmp_project, f"{parent.id}@0")) == []
    parent_file = find(tmp_project, parent.id)
    before = parent_file.read_text()
    child, _ = replay(at_two)
    child.append(Message("user", (TextBlock("two b"),)))
    assert texts(at_two) == ["one", "two", "two b"]
    assert parent_file.read_text() == before


def test_a_fork_of_a_fork_resolves_through_both(tmp_project: Path) -> None:
    parent = talk(tmp_project, "one", "two")
    first = fork(tmp_project, f"{parent.id}@1")
    child, _ = replay(first)
    for text in ("one b", "one c"):
        child.append(Message("user", (TextBlock(text),)))
        child.record({"type": "event", "event": "TurnFinished", "turn": 1})
    second = fork(tmp_project, f"{first.stem}@2")  # the parent's turn one, then its own first
    assert texts(second) == ["one", "one b"]
    assert [e["type"] for e in chain(second)][:1] == ["session"]


def test_a_session_with_forks_is_not_removed(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parent = talk(tmp_project, "one")
    child = fork(tmp_project, parent.id)
    with pytest.raises(UsageError, match=f"has forks: {child.stem}"):
        command(["sessions", "rm", parent.id], tmp_project, home)
    assert command(["sessions", "rm", child.stem], tmp_project, home) == 0
    assert command(["sessions", "rm", parent.id], tmp_project, home) == 0
    assert list(sessions_dir(tmp_project).glob("*.jsonl")) == []


@pytest.mark.parametrize("turn", ["4", "x", "-1"])
def test_a_turn_the_parent_never_reached_is_refused(tmp_project: Path, turn: str) -> None:
    parent = talk(tmp_project, "one", "two", "three")
    with pytest.raises(UsageError, match="turns 0 to 3"):
        fork(tmp_project, f"{parent.id}@{turn}")


def test_save_inlines_spilled_output_and_redacts_secrets(tmp_project: Path) -> None:
    session = talk(tmp_project, "read the log")
    blob = tmp_project / "spilled.txt"
    blob.write_text("line " * 50 + "token=hunter2", encoding="utf-8")
    call = Message("assistant", (ToolUseBlock("tu_1", "read", {"path": "log"}),))
    result = ToolResultBlock("tu_1", (TextBlock("line line …"),), truncated=True, blob=str(blob))
    session.append(call)
    session.append(Message("tool", (result,)))
    key = "sk-" + "a1B2" * 8
    session.record({"type": "title", "text": f"debug with {key}"})
    out = tmp_project / "shared.jsonl"
    save(find(tmp_project, session.id), out)  # [CLI-25, MEM-15]
    raw = out.read_text(encoding="utf-8")
    assert "hunter2" not in raw and "a1B2" not in raw and "spilled.txt" not in raw
    lines = [json.loads(line) for line in raw.splitlines()]
    (tool,) = [e for e in lines if e["type"] == "message" and e["role"] == "tool"]
    block = tool["content"][0]
    assert (block["blob"], block["truncated"]) == (None, False)
    assert block["content"][0]["text"].startswith("line line line")
    elsewhere = tmp_project.parent / "elsewhere"
    elsewhere.mkdir()
    loaded, _ = replay(adopt(elsewhere, out))
    assert loaded.cwd == elsewhere and loaded.id != session.id
    assert [m.role for m in loaded.transcript] == ["user", "assistant", "assistant", "tool"]
    with pytest.raises(UsageError, match="not a file"):
        adopt(elsewhere, elsewhere / "missing.jsonl")


def test_history_keeps_what_compaction_took_from_the_view(tmp_project: Path) -> None:
    session = talk(tmp_project, "one", "two")
    session.record({"type": "reset"})
    path = find(tmp_project, session.id)
    assert texts(path) == []
    assert [m.text for m in conversation(path)] == ["one", "re one", "two", "re two"]


def test_fork_and_load_on_the_command_line(
    tmp_project: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = talk(tmp_project, "one", "two")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr("sys.stdin", None)  # nothing piped
    base = ["--cwd", str(tmp_project), "--model", "fake/test", "--mode", "ask", "-p"]
    assert main([*base, "three", "--fork", f"{parent.id}@1"]) == 0
    assert len(list(sessions_dir(tmp_project).glob("*.jsonl"))) == 2
    newest = find(tmp_project, "")
    assert texts(newest) == ["one", "three"]  # [CLI-22]
    save(newest, tmp_project / "out.jsonl")
    assert main([*base, "four", "--load", str(tmp_project / "out.jsonl")]) == 0
    assert texts(find(tmp_project, "")) == ["one", "three", "four"]
    assert main([*base, "x", "--fork", f"{parent.id}@9"]) == 2
    assert "turns 0 to 2" in capsys.readouterr().err


def _setup(root: Path, home: Path, cap: float | None, turn: float | None = None) -> Setup:
    budget = BudgetSection(daily_cost_cap=cap, turn_cost_cap=turn)
    return setup(
        root, Config(model=ModelSection(default="fake/test"), budget=budget), home=home, env={}
    )


def ended(cost: float | None, depth: int = 0) -> TurnFinished:
    return TurnFinished(turn_id="t", usage=Usage(), cost=cost, reason="done", depth=depth)


def test_the_daily_cap_becomes_the_turns_cap_and_then_stops_turns(
    tmp_project: Path, home: Path
) -> None:
    s = _setup(tmp_project, home, cap=0.01, turn=0.05)
    bus = EventBus()
    _, rt = begin(s, bus)
    bus.emit(ended(0.004))  # recorded [BUD-2]
    bus.emit(ended(None))  # unknown pricing: nothing to add [BUD-5]
    bus.emit(ended(0.9, depth=1))  # a subagent's: its parent's turn carries it
    assert [cost for _, cost in spending(home).spent()] == [0.004]
    assert daily(s, rt).budget.turn_cost_cap == pytest.approx(0.006)
    spending(home).spend(0.006)
    with pytest.raises(BudgetExceeded, match="daily_cost_cap") as caught:
        daily(s, rt)
    assert caught.value.exit_code == 6  # [BUD-3]
    unset = _setup(tmp_project, home, cap=None)
    assert daily(unset, rt) is rt


def test_p_exits_6_when_the_day_is_spent(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text("[budget]\ndaily_cost_cap = 0.5\n")
    spending(home).spend(0.5)
    with pytest.raises(BudgetExceeded):
        run_prompt("hi", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home)
    assert command(["cost"], tmp_project, home) == 0  # [BUD-6]
    shown = capsys.readouterr().out
    assert "today $0.5000 of daily_cost_cap $0.50" in shown and "not counted" in shown
