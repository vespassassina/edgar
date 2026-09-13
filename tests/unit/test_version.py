from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import edgar
from edgar.cli.main import main

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_matches_pyproject() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert edgar.__version__ == project["version"]


def test_version_goes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    out, err = capsys.readouterr()
    assert out == f"edgar {edgar.__version__}\n"
    assert err == ""


def test_nothing_to_run_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    out, err = capsys.readouterr()
    assert out == ""  # stdout is the result; there is none [CLI-5]
    assert "REPL arrives in M4" in err


def test_unknown_flag_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--no-such-flag"])
    assert exit_info.value.code == 2
