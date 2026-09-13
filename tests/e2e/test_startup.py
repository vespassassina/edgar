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
