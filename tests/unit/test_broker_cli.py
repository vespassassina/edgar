"""`edgar receipt [ID] [--refused] [--verify]` [ADR-0039]."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.broker.cli import command
from edgar.broker.receipt import Receipts, load_or_create_key
from edgar.core.message import Message, TextBlock
from edgar.core.session import Session
from edgar.storage.transcript import start


def new_session(tmp_project: Path) -> Session:
    session = start(Session(cwd=tmp_project, model="fake/test", mode="ask"))
    session.append(Message("user", (TextBlock("hello"),)))  # so its transcript file exists
    return session


def seeded(tmp_project: Path, home: Path) -> Session:
    session = new_session(tmp_project)
    receipts = Receipts(path=session.dir / "receipt.jsonl", key=load_or_create_key(home))
    receipts.record("intent", {"text": "do the thing"})
    receipts.record("refuse", {"tool": "read", "caveat": "paths", "reason": "outside scope"})
    return session


def test_command_tells_the_story_for_the_latest_session_by_default(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seeded(tmp_project, home)
    assert command([], tmp_project, home) == 0
    out = capsys.readouterr().out
    assert "intent: " in out and "refuse: " in out


def test_command_by_id_narrows_to_refused_with_the_flag(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = seeded(tmp_project, home)
    assert command([session.id, "--refused"], tmp_project, home) == 0
    out = capsys.readouterr().out
    assert "intent: " not in out and "refuse: " in out


def test_command_verify_holds_for_an_honest_receipt(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seeded(tmp_project, home)
    assert command(["--verify"], tmp_project, home) == 0
    assert "every line still holds" in capsys.readouterr().out


def test_command_verify_catches_a_tamper_and_exits_1(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = seeded(tmp_project, home)
    path = session.dir / "receipt.jsonl"
    path.write_text(path.read_text().replace("do the thing", "do something else"))
    assert command(["--verify"], tmp_project, home) == 1
    assert "line 1" in capsys.readouterr().err


def test_command_with_no_receipt_yet_fails_clearly(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = new_session(tmp_project)
    assert command([], tmp_project, home) == 1
    assert f"no receipt for {session.id}" in capsys.readouterr().err


def test_command_rejects_more_than_one_id(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["a", "b"], tmp_project, home) == 2
    assert "usage" in capsys.readouterr().err
