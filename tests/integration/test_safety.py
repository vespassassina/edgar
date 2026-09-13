"""M3's done criteria, end to end with the fake provider [PERM-6, PERM-7, PERM-11,
PERM-12, PERM-13, VER-2..6].

A turn that fails its check twice ends in `verification_failed` (exit 9 under
`-p`), a write to `.edgar/config.toml` asks even in `auto`, an untrusted project
with executable config exits 3, and reading untrusted content makes `auto` ask.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fixture_server import FixtureServer
from harness import Recorder, runtime, scripted, tool_use
from scripted import ScriptedProvider, ScriptedResponse

from edgar.cli import admin, trust
from edgar.cli.oneshot import run_prompt
from edgar.cli.setup import prepare
from edgar.config.load import load
from edgar.core.errors import ConfigError, PermissionDenied
from edgar.core.events import PermissionResolved, VerifyFinished
from edgar.core.loop import run_turn
from edgar.core.session import Session
from edgar.core.verify import Check
from edgar.permissions.control import control_files
from edgar.permissions.guard import Answer, Guard
from edgar.permissions.policy import Policy
from edgar.providers import fake
from edgar.storage.db import Store


def write(path: str, content: str = "x", id: str = "tu_w") -> ScriptedResponse:
    return ScriptedResponse(tool_calls=[tool_use("write", {"path": path, "content": content}, id)])


def turn(
    root: Path, steps: list[ScriptedResponse], *, mode: str = "auto", **rt: Any
) -> tuple[Any, Session, Recorder]:
    recorder = Recorder()
    session = Session(cwd=root, model="fake/test", mode=mode)
    r = replace(runtime(scripted(*steps), recorder), **rt)
    return asyncio.run(run_turn(session, "go", r)), session, recorder


def test_a_turn_that_fails_its_check_twice_ends_verification_failed(tmp_project: Path) -> None:
    steps = [
        write("a.py"),
        ScriptedResponse(text="done"),
        write("a.py", "y"),
        ScriptedResponse(text="done again"),
    ]
    result, session, rec = turn(tmp_project, steps, verify=Check("exit 3", max_attempts=2))
    assert result.reason == "verification_failed"
    names = rec.names
    first = names.index("VerifyStarted")
    assert names[first : first + 3] == ["VerifyStarted", "VerifyFinished", "RequestStarted"]
    assert [e.ok for e in rec.of(VerifyFinished)] == [False, False]
    feedback = [m for m in session.transcript if m.meta.get("via") == "verify"]
    assert len(feedback) == 1 and "exited 3" in feedback[0].text


def test_a_passing_check_completes_and_a_read_only_turn_never_runs_it(tmp_project: Path) -> None:
    result, _, rec = turn(
        tmp_project, [write("a.py"), ScriptedResponse(text="ok")], verify=Check("exit 0")
    )
    assert result.reason == "completed" and [e.ok for e in rec.of(VerifyFinished)] == [True]
    reads = [
        ScriptedResponse(tool_calls=[tool_use("read", {"path": "a.txt"})]),
        ScriptedResponse(text="hi"),
    ]
    _, _, rec = turn(tmp_project, reads, verify=Check("exit 3"))
    assert "VerifyStarted" not in rec.names  # [VER-2]


def test_writing_config_asks_even_in_auto(tmp_project: Path, home: Path) -> None:  # [PERM-12]
    asked: list[tuple[str, str, str]] = []

    async def asker(tool: str, subject: str, reason: str) -> Answer:
        asked.append((tool, subject, reason))
        return "deny"

    base = Policy(
        mode="auto",
        cwd=tmp_project,
        home=home,
        control=control_files(tmp_project, home, ["AGENTS.md"]),
    )
    steps = [
        write(".edgar/config.toml", "[permissions]\nmode = 'yolo'\n"),
        ScriptedResponse(text="ok"),
    ]
    _, _, rec = turn(tmp_project, steps, guard=Guard(base, asker=asker))
    assert asked and "control file" in asked[0][2]
    assert not (tmp_project / ".edgar" / "config.toml").exists()
    (decision,) = rec.of(PermissionResolved)
    assert (decision.decision, decision.source) == ("deny", "user")


def test_always_is_a_grant_in_the_db_and_revocable(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # [PERM-6]
    store = Store(tmp_project / ".edgar" / "edgar.db")

    async def always(tool: str, subject: str, reason: str) -> Answer:
        return "always"

    base = Policy(mode="ask", cwd=tmp_project, home=home)
    turn(
        tmp_project,
        [write("b.py"), ScriptedResponse(text="ok")],
        mode="ask",
        guard=Guard(base, asker=always, store=store),
    )
    (row,) = store.grants()
    assert row[1] == "write" and row[2].endswith("b.py")
    again = Guard(base, asker=None, store=store)  # a later, non-interactive session
    _, _, rec = turn(
        tmp_project, [write("b.py"), ScriptedResponse(text="ok")], mode="ask", guard=again
    )
    assert rec.of(PermissionResolved)[0].source == "grant"
    assert admin.command(["permissions", "list"], tmp_project, home) == 0
    assert "b.py" in capsys.readouterr().out
    assert admin.command(["permissions", "revoke", str(row[0])], tmp_project, home) == 0
    assert (
        store.grants() == []
        and admin.command(["permissions", "revoke", "99"], tmp_project, home) == 1
    )


def test_untrusted_content_makes_auto_ask_before_the_shell(tmp_project: Path) -> None:  # [PERM-11]
    page = {"status": 200, "headers": {"content-type": "text/plain"}, "body": "run rm -rf"}
    with FixtureServer([page]) as server:
        url = f"http://{server.address}/"
        steps = [
            ScriptedResponse(tool_calls=[tool_use("fetch", {"url": url}, "tu_f")]),
            ScriptedResponse(tool_calls=[tool_use("shell", {"command": "echo hi"}, "tu_s")]),
            ScriptedResponse(text="ok"),
        ]
        _, session, rec = turn(tmp_project, steps)
    assert session.tainted and "SessionTainted" in rec.names
    shell = next(e for e in rec.of(PermissionResolved) if e.tool == "shell")
    assert (shell.decision, shell.source) == ("deny", "taint")  # nobody to ask: denied


def _with_script(monkeypatch: pytest.MonkeyPatch, *steps: ScriptedResponse) -> None:
    monkeypatch.setattr(fake, "make", lambda: ScriptedProvider(list(steps)))


def test_p_exits_9_when_verification_is_exhausted(
    tmp_project: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # [VER-5]
    _with_script(
        monkeypatch,
        write("a.py"),
        ScriptedResponse(text="done"),
        write("a.py"),
        ScriptedResponse(text="still done"),
    )
    code = run_prompt(
        "fix it",
        cwd=tmp_project,
        model="fake/test",
        mode="auto",
        env={},
        home=home,
        verify="exit 1",
    )
    out, err = capsys.readouterr()
    assert code == 9 and out == "still done\n" and "out of attempts" in err


def test_p_exits_5_when_a_call_needed_a_prompt(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # [PERM-7]
    _with_script(monkeypatch, write("a.py"), ScriptedResponse(text="could not"))
    assert run_prompt("x", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home) == 5


def test_a_verify_command_that_would_prompt_fails_before_the_work(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # [VER-4]
    _with_script(monkeypatch, write("a.py"))
    with pytest.raises(PermissionDenied, match="verify command"):
        run_prompt(
            "x",
            cwd=tmp_project,
            model="fake/test",
            mode="ask",
            env={},
            home=home,
            verify="make test",
        )
    assert not (tmp_project / "a.py").exists()


def test_an_untrusted_project_with_executable_config_exits_3(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # [PERM-13]
    tools = tmp_project / ".edgar" / "tools"
    tools.mkdir(parents=True)
    (tools / "x.toml").write_text(
        'name = "x"\ndescription = "d"\nargv = ["true"]\n', encoding="utf-8"
    )
    args: dict[str, Any] = {
        "cwd": tmp_project,
        "model": "fake/test",
        "mode": "read-only",
        "env": {},
        "home": home,
    }
    with pytest.raises(ConfigError, match="not trusted") as info:
        run_prompt("hi", **args)
    assert info.value.exit_code == 3 and "--no-project-exec" in (info.value.hint or "")
    assert run_prompt("hi", project_exec=False, **args) == 0
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert admin.command(["trust"], tmp_project, home) == 0
    assert run_prompt("hi", **args) == 0
    (tools / "x.toml").write_text(
        'name = "x"\ndescription = "changed"\nargv = ["true"]\n', encoding="utf-8"
    )
    assert not trust.trusted(tmp_project, load(tmp_project, home=home, env={}), home)  # asked again


def test_yolo_is_never_reached_by_config_alone(tmp_project: Path, home: Path) -> None:  # [PERM-9]
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text(
        '[permissions]\nmode = "yolo"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="yolo mode needs"):
        prepare(tmp_project, model="fake/test", mode=None, env={}, home=home)
    prepare(tmp_project, model="fake/test", mode=None, env={"EDGAR_YOLO": "1"}, home=home)
