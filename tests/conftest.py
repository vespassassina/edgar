from __future__ import annotations

import os
import sys
from pathlib import Path

import netguard
import pytest

SUPPORT = Path(__file__).parent / "support"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any socket call. Applied to the whole offline suite."""
    for owner, name, replacement in netguard.PATCHES:
        monkeypatch.setattr(owner, name, replacement)


@pytest.fixture
def subprocess_env(tmp_path: Path) -> dict[str, str]:
    """Environment for e2e subprocesses: puts tests/support/ on PYTHONPATH so its
    sitecustomize.py installs the same socket guard inside the child process."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EDGAR_")}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SUPPORT), env.get("PYTHONPATH")]))
    env["HOME"] = env["USERPROFILE"] = str(tmp_path / "home")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.fixture
def edgar_argv() -> list[str]:
    """How to start the installed CLI from a test, the same on every platform."""
    return [sys.executable, "-m", "edgar"]
