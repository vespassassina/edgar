"""A `[providers.NAME]` block reaches a server with no code change [PRV-12].

M2's done criterion, end to end: config names a server, `edgar -p` talks to it
over a real socket, the answer comes back on stdout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fixture_server import FixtureServer
from harness import Recorder
from wire import Reply, ok, openai_sse

from edgar.cli.oneshot import run_prompt
from edgar.core.events import RequestFinished

LOCAL = '[providers.local]\nkind = "openai-compatible"\nbase_url = "{url}"\n'


def _configure(project: Path, url: str) -> None:
    path = project / ".edgar" / "config.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(LOCAL.format(url=url), encoding="utf-8")


def test_a_config_block_reaches_a_local_server(
    tmp_project: Path, home: Path, recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    with FixtureServer(
        [ok(openai_sse(Reply(text="Hello from a local server."), "compat"))]
    ) as server:
        _configure(tmp_project, server.base_url)
        code = run_prompt(
            "hi",
            cwd=tmp_project,
            model="local/qwen3-8b",
            mode="read-only",
            subscribers=[recorder],
            env={},
            home=home,
        )
    assert code == 0
    assert capsys.readouterr().out == "Hello from a local server.\n"
    (request,) = server.requests
    assert request.url == "/v1/chat/completions"
    assert request.body["model"] == "qwen3-8b"
    assert "authorization" not in {k.lower() for k in request.headers}  # no key configured
    (finished,) = recorder.of(RequestFinished)
    assert finished.cost is None  # nobody priced this server: unknown, not zero


def test_the_same_from_the_command_line(
    tmp_project: Path, edgar_argv: list[str], subprocess_env: dict[str, str]
) -> None:
    with FixtureServer([ok(openai_sse(Reply(text="From the child."), "compat"))]) as server:
        _configure(tmp_project, server.base_url)
        env = subprocess_env | {"EDGAR_TEST_NET_ALLOW": server.address}
        argv = [*edgar_argv, "-p", "hi", "--model", "local/m", "--mode", "read-only"]
        out = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=tmp_project)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "From the child.\n"
