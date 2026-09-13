from __future__ import annotations

import os
import sys
from pathlib import Path

import netguard
import pytest
from harness import Recorder

SUPPORT = Path(__file__).parent / "support"

pytest_plugins = ["rig"]  # the contract suite's `rig` fixture


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("edgar")
    group.addoption("--live", action="store_true", help="contract suite against real APIs")
    group.addoption(
        "--record", metavar="PROVIDER", help="re-record that provider's cassettes (implies --live)"
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Fail loudly on any socket call. Applied to the whole offline suite; lifted
    only by --live or --record, which exist to reach real APIs."""
    if request.config.getoption("--live") or request.config.getoption("--record"):
        return
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


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A working directory with a small file to read. No .edgar/ yet: that is M5."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    (root / "src").mkdir()
    return root


@pytest.fixture
def recorder() -> Recorder:
    """Subscriber capturing the event stream for assertion."""
    return Recorder()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """An empty home directory, so a real ~/.edgar never leaks into a test."""
    path = tmp_path / "home"
    path.mkdir()
    return path
