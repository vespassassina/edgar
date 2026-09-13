from __future__ import annotations

import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

import edgar


def _console_script(name: str) -> str:
    scripts = Path(sysconfig.get_path("scripts"))
    found = shutil.which(name, path=str(scripts))
    assert found, f"{name} console script not installed in {scripts}"
    return found


def test_module_entry_point(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [*edgar_argv, "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout, out.stderr) == (0, f"edgar {edgar.__version__}\n", "")


@pytest.mark.parametrize("name", ["edgar", "edgar-harness"])  # uvx needs the second
def test_console_scripts(name: str, subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [_console_script(name), "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout) == (0, f"edgar {edgar.__version__}\n")


def test_read_a_file_through_the_real_cli(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # M1's "done when", as a user would type it [CLI-2, CLI-5].
    argv = [*edgar_argv, "-p", "read a.txt", "--model", "fake/test", "--mode", "read-only"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert (out.returncode, out.stdout, out.stderr) == (0, "     1\thello\n     2\tworld\n", "")


def test_errors_go_to_stderr_with_a_hint_and_an_exit_code(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    argv = [*edgar_argv, "-p", "hi", "--model", "fake/test"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert out.returncode == 3 and out.stdout == ""
    assert "explicit --mode" in out.stderr and "hint:" in out.stderr


def test_prompt_show(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [*edgar_argv, "prompt", "show"], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode == 0
    assert out.stdout.startswith("You are running inside edgar")
    assert "tokens of 1,500" in out.stderr


def test_child_processes_are_offline_too(subprocess_env: dict[str, str]) -> None:
    code = "import socket; socket.create_connection(('example.com', 443))"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode != 0
    assert "NetworkBlocked" in out.stderr
