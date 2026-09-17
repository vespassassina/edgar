"""`edgar -p` in process: M1's "done when" [CLI-2, CLI-9, CFG-3]."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from harness import Recorder

from edgar.cli.oneshot import run_prompt
from edgar.core.errors import ConfigError
from edgar.core.events import ModelSelected
from edgar.core.message import Message, TextBlock


def test_read_a_file_with_the_fake_model(
    tmp_project: Path, home: Path, recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_prompt(
        "read a.txt",
        cwd=tmp_project,
        model="fake/test",
        mode="read-only",
        subscribers=[recorder],
        env={},
        home=home,
    )
    out, err = capsys.readouterr()
    assert code == 0
    assert out == "     1\thello\n     2\tworld\n"
    assert err == ""
    assert recorder.names == [
        "ModelSelected",
        "SessionStarted",
        "TurnStarted",
        "RequestStarted",
        "RequestFinished",
        "ToolProposed",
        "PermissionResolved",
        "ToolStarted",
        "ToolFinished",
        "RequestStarted",
        "TextDelta",
        "RequestFinished",
        "TurnFinished",
        "SessionEnded",
    ]


def test_mode_is_required(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="explicit --mode") as info:
        run_prompt("hi", cwd=tmp_project, model="fake/test", mode=None, env={}, home=home)
    assert info.value.exit_code == 3


def test_model_can_come_from_project_config(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/test"\n')
    assert run_prompt("hi", cwd=tmp_project, model=None, mode="ask", env={}, home=home) == 0
    assert capsys.readouterr().out == "fake/test heard: hi\n"


def test_a_route_rule_keyed_on_mode_matches_the_main_turn(
    tmp_project: Path, home: Path, recorder: Recorder
) -> None:
    """The main turn's `RoutingContext` used to be built with every field left at
    its default, so a `[[route]]` rule keyed on `mode` could never match it. Fixed
    in `cli/setup.py`'s `runtime()`, which now passes the mode the CLI resolved."""
    (tmp_project / ".edgar").mkdir()
    (tmp_project / ".edgar" / "config.toml").write_text(
        '[model]\ndefault = "fake/wrong-if-picked"\n\n'
        '[[route]]\nname = "read-only-goes-cheap"\nmodel = "fake/test"\nmode = "read-only"\n'
    )
    run_prompt(
        "hi",
        cwd=tmp_project,
        model=None,
        mode="read-only",
        subscribers=[recorder],
        env={},
        home=home,
    )
    selected = recorder.of(ModelSelected)[0]
    assert (selected.model, selected.rule) == ("fake/test", "read-only-goes-cheap")


def test_no_model_anywhere_is_a_config_error(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="no model configured"):
        run_prompt("hi", cwd=tmp_project, model=None, mode="ask", env={}, home=home)


def test_bad_config_names_file_key_and_type(tmp_project: Path, home: Path) -> None:
    config = tmp_project / ".edgar" / "config.toml"
    config.parent.mkdir()
    config.write_text('[tools]\nmax_output_tokens = "8k"\n')
    with pytest.raises(ConfigError) as info:
        run_prompt("hi", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home)
    message = str(info.value)
    assert str(config) in message
    assert "[tools] max_output_tokens" in message
    assert "an integer" in message


def test_unknown_provider_is_a_config_error(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="unknown provider 'gemini'") as info:
        run_prompt("hi", cwd=tmp_project, model="gemini/pro", mode="ask", env={}, home=home)
    assert "[providers.gemini]" in (info.value.hint or "")


def test_a_missing_key_is_a_config_error_naming_the_variable(tmp_project: Path, home: Path) -> None:
    # Checked before any request, so a missing key never costs a network call.
    with pytest.raises(ConfigError, match="OPENAI_API_KEY is not set") as info:
        run_prompt("hi", cwd=tmp_project, model="openai/gpt-5", mode="ask", env={}, home=home)
    assert info.value.exit_code == 3


def test_json_is_one_object_with_the_result_and_what_it_took(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # [CLI-7]
    run_prompt(
        "read a.txt",
        cwd=tmp_project,
        model="fake/test",
        mode="read-only",
        env={},
        home=home,
        output="json",
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "     1\thello\n     2\tworld"
    assert (payload["tools"], payload["reason"], payload["cost"]) == (["read"], "completed", 0.0)
    assert payload["usage"]["input_tokens"] > 0 and payload["model"] == "fake/test"


def test_events_are_json_lines_on_stdout(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # [CLI-18]
    run_prompt(
        "read a.txt",
        cwd=tmp_project,
        model="fake/test",
        mode="read-only",
        env={},
        home=home,
        output="events",
    )
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    names = [line["event"] for line in lines]
    assert names[0] == "ModelSelected" and names[-1] == "SessionEnded"
    assert "ToolFinished" in names and all("agent_id" in line for line in lines)


def test_stdin_is_attached_context_not_the_prompt(tmp_project: Path, home: Path) -> None:  # [CLI-3]
    from edgar.providers import fake

    seen: list[Message] = []
    original = fake.FakeProvider.stream

    async def spy(self: fake.FakeProvider, messages: Any, *args: Any, **kwargs: Any) -> Any:
        seen.extend(messages)
        return await original(self, messages, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fake.FakeProvider, "stream", spy)
        run_prompt(
            "review this",
            cwd=tmp_project,
            model="fake/test",
            mode="read-only",
            env={},
            home=home,
            attached="diff --git a/x b/x",
        )
    prompt, context = seen[-1].content
    assert isinstance(prompt, TextBlock) and isinstance(context, TextBlock)
    assert (prompt.text, prompt.attached) == ("review this", False)
    assert context.attached and "<attached>\ndiff --git a/x b/x\n</attached>" in context.text


def test_a_typed_keyword_loads_a_skills_body_without_the_model_asking(
    tmp_project: Path, home: Path
) -> None:  # [SKL-17]
    from edgar.providers import fake

    folder = tmp_project / ".edgar" / "skills" / "deploy"
    folder.mkdir(parents=True)
    text = (
        "---\nname: deploy\ndescription: Use when deploying.\n"
        "when: {keywords: [deploy]}\n---\nRun `just ship`.\n"
    )
    (folder / "SKILL.md").write_text(text, encoding="utf-8")

    seen: list[Message] = []
    original = fake.FakeProvider.stream

    async def spy(self: fake.FakeProvider, messages: Any, *args: Any, **kwargs: Any) -> Any:
        seen.extend(messages)
        return await original(self, messages, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fake.FakeProvider, "stream", spy)
        run_prompt(
            "please deploy this",
            cwd=tmp_project,
            model="fake/test",
            mode="read-only",
            env={},
            home=home,
        )
    _prompt, context = seen[-1].content
    assert isinstance(context, TextBlock)
    assert "skill deploy" in context.text and "Run `just ship`." in context.text


def test_the_status_line_never_reaches_stdout(
    tmp_project: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # [CLI-5, CLI-6]: `edgar -p hi > out.txt` has no ANSI bytes, even on a terminal
    from edgar.cli import oneshot

    monkeypatch.setattr(oneshot, "terminal_ready", lambda stream: True)
    run_prompt("hi", cwd=tmp_project, model="fake/test", mode="read-only", env={}, home=home)
    out, err = capsys.readouterr()
    assert out == "fake/test heard: hi\n" and "\x1b" not in out
    assert "\x1b[2K" in err  # it drew, and cleared, on stderr


def test_quiet_turns_the_status_line_off(
    tmp_project: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # [CLI-8]
    from edgar.cli import oneshot

    monkeypatch.setattr(oneshot, "terminal_ready", lambda stream: True)
    run_prompt(
        "hi", cwd=tmp_project, model="fake/test", mode="read-only", env={}, home=home, quiet=True
    )
    assert capsys.readouterr().err == ""
