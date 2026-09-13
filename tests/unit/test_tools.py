"""The M3 built-ins, and command and HTTP tools [TOOL-5, TOOL-6, TOOL-9, TOOL-11, TOOL-13]."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fixture_server import FixtureServer

from edgar.core.errors import ConfigError
from edgar.core.events import EventBus
from edgar.tools.base import Tool, ToolContext, ToolResult
from edgar.tools.builtin.fs import builtins
from edgar.tools.builtin.shell import run_argv, shell_argv
from edgar.tools.custom import SECRETS, load
from edgar.tools.registry import registry_for

TOOLS: dict[str, Tool] = {t.schema.name: t for t in builtins()}


def run(tool: Tool | str, args: dict[str, Any], cwd: Path) -> ToolResult:
    t = TOOLS[tool] if isinstance(tool, str) else tool
    ctx = ToolContext(cwd=cwd, bus=EventBus(), blob_dir=cwd / "blobs", max_output_tokens=8000)
    return asyncio.run(t.run(args, ctx))


def test_write_then_edit(tmp_project: Path) -> None:
    assert run("write", {"path": "new/x.py", "content": "a = 1\na = 1\n"}, tmp_project).text == (
        "created new/x.py"
    )
    twice = run("edit", {"path": "new/x.py", "old": "a = 1", "new": "b"}, tmp_project)
    assert twice.error == "validation" and "2 times" in twice.text
    done = run(
        "edit", {"path": "new/x.py", "old": "a = 1", "new": "b", "replace_all": True}, tmp_project
    )
    assert done.text == "edited new/x.py: 2 replacements"
    assert (tmp_project / "new" / "x.py").read_text(encoding="utf-8") == "b\nb\n"
    assert (
        run("edit", {"path": "new/x.py", "old": "zzz", "new": ""}, tmp_project).error
        == "validation"
    )
    assert run("edit", {"path": "nope", "old": "a", "new": ""}, tmp_project).error == "not_found"
    assert run("write", {"path": "a.txt", "content": "x"}, tmp_project).text == "overwrote a.txt"


def test_glob_and_grep_stay_inside(tmp_project: Path) -> None:
    (tmp_project / "src" / "m.py").write_text("def auth():\n    return 1\n", encoding="utf-8")
    (tmp_project / "src" / "bin.dat").write_bytes(b"\0auth")
    (tmp_project / ".git").mkdir()
    (tmp_project / ".git" / "auth.py").write_text("auth", encoding="utf-8")
    assert run("glob", {"pattern": "**/*.py"}, tmp_project).text == "src/m.py"
    assert run("glob", {"pattern": "../*"}, tmp_project).text == "no matches"
    assert run("grep", {"pattern": "auth"}, tmp_project).text == "src/m.py:1:def auth():"
    assert run(
        "grep", {"pattern": "AUTH", "ignore_case": True, "glob": "src/*.py"}, tmp_project
    ).text
    assert run("grep", {"pattern": "("}, tmp_project).error == "validation"


def test_shell_reports_exit_code_and_program(tmp_project: Path) -> None:
    ok = run("shell", {"command": "echo hi"}, tmp_project)
    assert ok.text.startswith("exit 0\n") and "hi" in ok.text and ok.error is None
    bad = run("shell", {"command": "exit 3"}, tmp_project)
    assert (bad.error, bad.exit_code, bad.program) == ("nonzero_exit", 3, "exit")


def test_a_cancelled_process_dies_with_its_children(tmp_project: Path) -> None:  # [TOOL-10]
    async def cancel() -> float:
        task = asyncio.create_task(run_argv(shell_argv("auto", "sleep 30 | cat"), tmp_project))
        await asyncio.sleep(0.3)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - started

    assert asyncio.run(cancel()) < 5


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ("/bin/bash", ["/bin/bash", "-c", "ls"]),
        ("pwsh", ["pwsh", "-NoProfile", "-NonInteractive", "-Command", "ls"]),
        ("cmd.exe", ["cmd.exe", "/d", "/c", "ls"]),
    ],
)
def test_shell_argv(program: str, expected: list[str]) -> None:
    assert shell_argv(program, "ls") == expected


def test_fetch_strips_html_and_is_untrusted(tmp_project: Path) -> None:
    page = "<html><script>x()</script><p>Hello</p>\n<p>world</p></html>"
    exchange = {"status": 200, "headers": {"content-type": "text/html"}, "body": page}
    with FixtureServer([exchange]) as server:
        result = run("fetch", {"url": f"http://{server.address}/page"}, tmp_project)
    assert (
        result.text.startswith("HTTP 200") and "Hello" in result.text and "x()" not in result.text
    )
    assert TOOLS["fetch"].schema.untrusted_output


# command and HTTP tools [TOOL-6, J9]


def _tool(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.toml").write_text(text, encoding="utf-8")


ECHO = f"""
name = "echo_args"
description = "Print the argv it received."
argv = [{json.dumps(sys.executable)}, "-c", "import sys; print(sys.argv[1:])",
        "{{text}}", "--n={{n}}"]
[input]
type = "object"
required = ["text"]
properties.text = {{ type = "string" }}
properties.n = {{ type = "integer" }}
"""


def test_a_command_tool_passes_an_argument_as_one_argv_element(tmp_project: Path) -> None:
    _tool(tmp_project / ".edgar" / "tools", "echo", ECHO)
    (tool,) = load([(tmp_project / ".edgar" / "tools", "project")])
    result = run(tool, {"text": "; rm -rf ~"}, tmp_project)
    assert "['; rm -rf ~']" in result.text  # one element; the absent --n was dropped
    assert tool.subject({"text": "x", "n": 2}, tmp_project).command.endswith("x --n=2")  # type: ignore[union-attr]


STATUS = """
name = "service_status"
description = "Status of a service."
url = "http://{address}/api/{{service}}?q={{q}}"
headers = {{ Authorization = "Bearer ${{env:STATUS_TOKEN}}" }}
read_only = true
[input]
type = "object"
required = ["service"]
properties.service = {{ type = "string" }}
properties.q = {{ type = "string" }}
"""


def test_an_http_tool_keeps_its_host_and_never_shows_its_token(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STATUS_TOKEN", "s3cret-token-value")
    echo = {
        "status": 200,
        "headers": {"content-type": "text/plain"},
        "body": "you sent s3cret-token-value",
    }
    with FixtureServer([echo]) as server:
        _tool(tmp_project / ".edgar" / "tools", "status", STATUS.format(address=server.address))
        (tool,) = load([(tmp_project / ".edgar" / "tools", "project")])
        result = run(tool, {"service": "../../evil.com/x", "q": "a&b"}, tmp_project)
    request = server.requests[0]
    assert request.url == "/api/..%2F..%2Fevil.com%2Fx?q=a%26b"  # encoded: same host
    assert request.headers["Authorization"] == "Bearer s3cret-token-value"
    assert "s3cret-token-value" not in result.text and "[redacted]" in result.text
    assert "s3cret-token-value" in SECRETS
    assert "s3cret" not in tool.subject({"service": "x"}, tmp_project).text  # env unresolved
    assert tool.schema.untrusted_output and tool.schema.category == "network"


def test_a_missing_secret_is_a_tool_error(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STATUS_TOKEN", raising=False)
    _tool(tmp_project / "t", "status", STATUS.format(address="127.0.0.1:9"))
    (tool,) = load([(tmp_project / "t", "user")])
    assert "STATUS_TOKEN" in run(tool, {"service": "x"}, tmp_project).text


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('name = "x"\ndescription = "d"\nurl = "http://{host}/a"\n', "fixed host"),
        (
            'name = "x"\ndescription = "d"\nurl = "http://h/a"\nheaders = { A = "{x}" }\n',
            "never arguments",
        ),
        ('name = "x"\ndescription = "d"\n', "either argv"),
        ('name = "x"\ndescription = "d"\nargv = ["a"]\nshell = true\n', "unknown keys shell"),
        ('name = "bad name"\ndescription = "d"\nargv = ["a"]\n', "needs a name"),
        ('name = "x"\ndescription = "d"\nargv = []\n', "non-empty"),
        ('name = "x"\ndescription = "d"\nargv = ["a"]\n[input]\ntype = "string"\n', "JSON Schema"),
        ("name = \n", "not valid TOML"),
    ],
)
def test_a_bad_tool_file_names_the_file(tmp_path: Path, text: str, problem: str) -> None:
    _tool(tmp_path, "bad", text)
    with pytest.raises(ConfigError) as info:
        load([(tmp_path, "project")])
    assert "bad.toml" in str(info.value) and problem in str(info.value)


def test_project_beats_user_beats_builtin_and_says_so(tmp_project: Path, home: Path) -> None:
    shadow = 'name = "read"\ndescription = "mine"\nargv = ["cat", "{path}"]\n'
    _tool(home / ".edgar" / "tools", "read", shadow)
    _tool(tmp_project / ".edgar" / "tools", "read", shadow.replace("mine", "project's"))
    registry = registry_for(tmp_project, home, shell="auto", project_exec=True)
    assert registry.get("read").schema.description == "project's"  # type: ignore[union-attr]
    assert len(registry.warnings) == 2
    untrusted = registry_for(tmp_project, home, shell="auto", project_exec=False)
    assert untrusted.get("read").schema.origin == "user"  # type: ignore[union-attr]
