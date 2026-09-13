from __future__ import annotations

import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import edgar


def _console_script() -> str:
    scripts = Path(sysconfig.get_path("scripts"))
    found = shutil.which("edgar", path=str(scripts))
    assert found, f"edgar console script not installed in {scripts}"
    return found


def test_module_entry_point(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [*edgar_argv, "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout, out.stderr) == (0, f"edgar {edgar.__version__}\n", "")


def test_console_script(subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [_console_script(), "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout) == (0, f"edgar {edgar.__version__}\n")


def test_child_processes_are_offline_too(subprocess_env: dict[str, str]) -> None:
    code = "import socket; socket.create_connection(('example.com', 443))"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode != 0
    assert "NetworkBlocked" in out.stderr
