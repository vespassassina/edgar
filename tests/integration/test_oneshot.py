"""`edgar -p` in process: M1's "done when" [CLI-2, CLI-9, CFG-3]."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import Recorder

from edgar.cli.oneshot import run_prompt
from edgar.core.errors import ConfigError


def test_read_a_file_with_the_fake_model(
    tmp_project: Path, home: Path, recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_prompt(
        "read a.txt",
        cwd=tmp_project,
        model="fake/test",
        mode="read-only",
        subscribers=[recorder],
        env={},
        home=home,
    )
    out, err = capsys.readouterr()
    assert code == 0
    assert out == "     1\thello\n     2\tworld\n"
    assert err == ""
    assert recorder.names == [
        "TurnStarted",
        "RequestStarted",
        "RequestFinished",
        "ToolProposed",
        "ToolStarted",
        "ToolFinished",
        "RequestStarted",
        "TextDelta",
        "RequestFinished",
        "TurnFinished",
    ]


def test_mode_is_required(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="explicit --mode") as info:
        run_prompt("hi", cwd=tmp_project, model="fake/test", mode=None, env={}, home=home)
    assert info.value.exit_code == 3


def test_model_can_come_from_project_config(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/test"\n')
    assert run_prompt("hi", cwd=tmp_project, model=None, mode="ask", env={}, home=home) == 0
    assert capsys.readouterr().out == "fake/test heard: hi\n"


def test_no_model_anywhere_is_a_config_error(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="no model configured"):
        run_prompt("hi", cwd=tmp_project, model=None, mode="ask", env={}, home=home)


def test_bad_config_names_file_key_and_type(tmp_project: Path, home: Path) -> None:
    config = tmp_project / ".edgar" / "config.toml"
    config.parent.mkdir()
    config.write_text('[tools]\nmax_output_tokens = "8k"\n')
    with pytest.raises(ConfigError) as info:
        run_prompt("hi", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home)
    message = str(info.value)
    assert str(config) in message
    assert "[tools] max_output_tokens" in message
    assert "an integer" in message


def test_unknown_provider_is_a_config_error(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="unknown provider 'openai'"):
        run_prompt("hi", cwd=tmp_project, model="openai/gpt-5", mode="ask", env={}, home=home)
