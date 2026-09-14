"""Startup budget [NFR-1, ADR-0012]. The import test is the one that holds."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

HEAVY = ("httpx", "rich", "prompt_toolkit", "jsonschema", "yaml", "keyring")


def test_cli_import_pulls_no_heavy_modules(subprocess_env: dict[str, str]) -> None:
    code = (
        "import sys, edgar.cli.main;"
        f"bad = [m for m in sys.modules if m.split('.')[0] in {HEAVY!r}"
        " or m.startswith('edgar.providers.')];"
        "print(bad)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", f"heavy imports at CLI import: {out.stdout}"


@pytest.mark.timing
def test_trivial_run_starts_fast(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    argv = [*edgar_argv, "-p", "hi", "--mode", "read-only", "--model", "fake/test"]
    start = time.perf_counter()
    subprocess.run(argv, check=True, capture_output=True, env=subprocess_env, cwd=tmp_project)
    assert time.perf_counter() - start < 0.5  # generous on shared CI; the import test holds


def test_five_mcp_servers_cost_a_run_nothing(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path, tmp_path: Path
) -> None:
    # Five servers configured, none started: a session that calls no MCP tool pays
    # the same as one with no servers at all [TOOL-8].
    fake = Path(__file__).parents[1] / "support" / "mcp_server.py"
    marks = tmp_path / "marks"
    blocks = [
        f'[mcp.s{n}]\ncommand = "{sys.executable}"\nargs = ["{fake.as_posix()}"]\n'
        f'env = {{ EDGAR_TEST_MARK = "{(marks / f"s{n}.txt").as_posix()}" }}\n'
        for n in range(5)
    ]
    config = Path(subprocess_env["HOME"]) / ".edgar" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("\n".join(blocks), encoding="utf-8")
    marks.mkdir()
    argv = [*edgar_argv, "-p", "hi", "--mode", "read-only", "--model", "fake/test"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert out.returncode == 0, out.stderr
    assert list(marks.iterdir()) == []  # not one of them was started


def test_cli_run_without_tools_stays_off_heavy_imports(
    subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # A run whose model calls no tool never needs jsonschema (NFR-1).
    code = (
        "import sys; from edgar.cli.main import main;"
        "main(['-p', 'hi', '--mode', 'read-only', '--model', 'fake/test']);"
        f"print([m for m in sys.modules if m.split('.')[0] in {HEAVY!r}], file=sys.stderr)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=subprocess_env,
        cwd=tmp_project,
    )
    assert out.returncode == 0, out.stderr
    assert out.stderr.strip() == "[]"
