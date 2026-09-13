"""Startup budget [NFR-1, ADR-0012]. The import test is the one that holds."""

from __future__ import annotations

import subprocess
import sys
import time

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
def test_version_starts_fast(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    # Becomes `-p hi --model fake/test` once M1 lands. Generous on shared CI.
    start = time.perf_counter()
    subprocess.run([*edgar_argv, "--version"], check=True, capture_output=True, env=subprocess_env)
    assert time.perf_counter() - start < 0.5
