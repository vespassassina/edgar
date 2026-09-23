"""edgar schedule list|add|remove|run, edgar tick/install-tick/uninstall-tick
[SCH-12]. install/tick are exercised through the real filesystem-backed pieces
they wire together; only the host installer is monkeypatched."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.schedule import cli as m
from edgar.schedule import install
from edgar.schedule.parser import load


def test_list_with_no_file_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert m.command(["schedule", "list"], tmp_path) == 0
    assert "no entries" in capsys.readouterr().out


def test_add_then_list_round_trips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = m.command(
        ["schedule", "add", "nightly", "--when", "@daily", "--prompt", "Summarise."],
        tmp_path,
    )
    assert rc == 0
    assert "added 'nightly'" in capsys.readouterr().out
    m.command(["schedule", "list"], tmp_path)
    assert "nightly" in capsys.readouterr().out


def test_add_with_scope_and_allowlist_flags(tmp_path: Path) -> None:
    rc = m.command(
        [
            "schedule",
            "add",
            "backup",
            "--when",
            "every 15m",
            "--prompt",
            "Back it up.",
            "--allowlist",
            "read,fetch",
            "--scope",
            "paths=reports/",
            "--catch-up",
            "all",
        ],
        tmp_path,
    )
    assert rc == 0
    (entry,) = load(tmp_path)
    assert entry.allowlist == ("read", "fetch")
    assert entry.scope == ("paths=reports/",)
    assert entry.catch_up == "all"


def test_add_with_a_bad_when_expression_fails_and_writes_nothing(tmp_path: Path) -> None:
    from edgar.core.errors import ConfigError

    with pytest.raises(ConfigError):
        m.command(["schedule", "add", "bad", "--when", "nonsense", "--prompt", "x"], tmp_path)
    assert load(tmp_path) == ()


def test_remove_an_unknown_name_reports_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert m.command(["schedule", "remove", "ghost"], tmp_path) == 1
    assert "no entry named" in capsys.readouterr().err


def test_remove_a_known_name_succeeds(tmp_path: Path) -> None:
    m.command(["schedule", "add", "a", "--when", "@daily", "--prompt", "p"], tmp_path)
    assert m.command(["schedule", "remove", "a"], tmp_path) == 0
    assert load(tmp_path) == ()


def test_run_an_unknown_name_reports_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert m.command(["schedule", "run", "ghost"], tmp_path) == 1
    assert "no entry named" in capsys.readouterr().err


def test_run_a_known_entry_uses_the_fake_provider(tmp_path: Path) -> None:
    m.command(
        ["schedule", "add", "a", "--when", "@daily", "--prompt", "hi", "--model", "fake/test"],
        tmp_path,
    )
    assert m.command(["schedule", "run", "a"], tmp_path) == 0


def test_tick_with_nothing_due_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    m.command(
        ["schedule", "add", "a", "--when", "@daily", "--prompt", "hi", "--model", "fake/test"],
        tmp_path,
    )
    m.command(["tick"], tmp_path)
    assert m.command(["tick"], tmp_path) == 0
    assert "nothing due" in capsys.readouterr().out


def test_tick_accepts_an_explicit_now(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    m.command(
        ["schedule", "add", "a", "--when", "@daily", "--prompt", "hi", "--model", "fake/test"],
        tmp_path,
    )
    assert m.command(["tick", "--now", "2026-09-23T10:00:00"], tmp_path) == 0
    assert "ran: a" in capsys.readouterr().out


def test_install_tick_and_uninstall_tick_delegate_to_the_host_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(install, "install", lambda cwd: "installed")
    monkeypatch.setattr(install, "uninstall", lambda cwd: "uninstalled")
    assert m.command(["install-tick"], tmp_path) == 0
    assert "installed" in capsys.readouterr().out
    assert m.command(["uninstall-tick"], tmp_path) == 0
    assert "uninstalled" in capsys.readouterr().out


def test_an_unrecognised_verb_prints_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert m.command(["schedule", "nonsense"], tmp_path) == 2
    assert "usage" in capsys.readouterr().err


def test_add_with_too_few_arguments_prints_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert m.command(["schedule", "add"], tmp_path) == 2
    assert "usage" in capsys.readouterr().err
