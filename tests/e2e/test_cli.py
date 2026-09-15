from __future__ import annotations

import json
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

import edgar


def _console_script(name: str) -> str:
    scripts = Path(sysconfig.get_path("scripts"))
    found = shutil.which(name, path=str(scripts))
    assert found, f"{name} console script not installed in {scripts}"
    return found


def test_module_entry_point(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [*edgar_argv, "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout, out.stderr) == (0, f"edgar {edgar.__version__}\n", "")


@pytest.mark.parametrize("name", ["edgar", "edgar-harness"])  # uvx needs the second
def test_console_scripts(name: str, subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [_console_script(name), "--version"], capture_output=True, text=True, env=subprocess_env
    )
    assert (out.returncode, out.stdout) == (0, f"edgar {edgar.__version__}\n")


def test_read_a_file_through_the_real_cli(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # M1's "done when", as a user would type it [CLI-2, CLI-5].
    argv = [*edgar_argv, "-p", "read a.txt", "--model", "fake/test", "--mode", "read-only"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert (out.returncode, out.stdout, out.stderr) == (0, "     1\thello\n     2\tworld\n", "")


def test_errors_go_to_stderr_with_a_hint_and_an_exit_code(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    argv = [*edgar_argv, "-p", "hi", "--model", "fake/test"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert out.returncode == 3 and out.stdout == ""
    assert "explicit --mode" in out.stderr and "hint:" in out.stderr


def test_prompt_show(edgar_argv: list[str], subprocess_env: dict[str, str]) -> None:
    out = subprocess.run(
        [*edgar_argv, "prompt", "show"], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode == 0
    assert out.stdout.startswith("You are running inside edgar")
    assert "tokens of 1,500" in out.stderr


def test_child_processes_are_offline_too(subprocess_env: dict[str, str]) -> None:
    code = "import socket; socket.create_connection(('example.com', 443))"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode != 0
    assert "NetworkBlocked" in out.stderr


def test_models_list_shows_where_prompts_can_go(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # Offline by construction: it reads config and the environment, nothing else [PRV-15].
    config = tmp_project / ".edgar" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[model]\ndefault = "anthropic/claude-sonnet-5"\ncompactor = "ollama/qwen3"\n'
        '[providers.lmstudio]\nkind = "openai-compatible"\nbase_url = "http://localhost:1234/v1"\n',
        encoding="utf-8",
    )
    env = subprocess_env | {"ANTHROPIC_API_KEY": "x"}
    env.pop("OPENAI_API_KEY", None)
    out = subprocess.run(
        [*edgar_argv, "models", "list"], capture_output=True, text=True, env=env, cwd=tmp_project
    )
    assert out.returncode == 0, out.stderr
    lines = {line.split()[0]: line for line in out.stdout.splitlines() if line.strip()}
    assert "anthropic/claude-sonnet-5" in lines["main"]
    assert "ollama/qwen3" in lines["compactor"] and "[model] compactor" in lines["compactor"]
    assert "no model of its own" in lines["controller"]
    assert "$ANTHROPIC_API_KEY (set)" in lines["anthropic"]
    assert "$OPENAI_API_KEY (unset)" in lines["openai"]
    assert "$AZURE_OPENAI_ENDPOINT" in lines["azure"]
    assert "http://localhost:1234/v1" in lines["lmstudio"] and "no key" in lines["lmstudio"]


def test_piped_stdin_events_and_no_escapes_on_stdout(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # `git diff | edgar -p "review this" --events` from a program [CLI-3, CLI-18].
    argv = [*edgar_argv, "-p", "review this", "--model", "fake/test", "--mode", "read-only"]
    out = subprocess.run(
        [*argv, "--events"],
        input="diff --git",
        capture_output=True,
        text=True,
        env=subprocess_env,
        cwd=tmp_project,
    )
    assert out.returncode == 0, out.stderr
    events = [json.loads(line) for line in out.stdout.splitlines()]
    assert events[-1]["event"] == "TurnFinished" and "\x1b" not in out.stdout
    texts = "".join(e["text"] for e in events if e["event"] == "TextDelta")
    assert "review this" in texts and "diff --git" in texts


def test_no_terminal_and_no_prompt_is_a_usage_error(
    edgar_argv: list[str], subprocess_env: dict[str, str]
) -> None:  # [CLI-4]
    out = subprocess.run(
        edgar_argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=subprocess_env
    )
    assert out.returncode == 2 and "use -p" in out.stderr


def test_j3_stdout_carries_only_the_answer(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # J3's acceptance: `edgar -p "hi" > out.txt 2>/dev/null` holds only the answer.
    argv = [*edgar_argv, "-p", "hi", "--model", "fake/test", "--mode", "read-only"]
    out = subprocess.run(argv, capture_output=True, text=True, env=subprocess_env, cwd=tmp_project)
    assert (out.returncode, out.stdout) == (0, "fake/test heard: hi\n")


def test_j9_the_example_tools_from_the_docs(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # J9, as a user would do it from examples/README.md: copy two tools in, find
    # the untrusted project refused (exit 3, naming `edgar trust`), trust it, list.
    examples = Path(__file__).resolve().parents[2] / "examples"
    shutil.copytree(examples / "tools", tmp_project / ".edgar" / "tools")
    shutil.copytree(examples / "skills", tmp_project / ".edgar" / "skills")

    def edgar(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*edgar_argv, *args],
            capture_output=True,
            text=True,
            env=subprocess_env,
            cwd=tmp_project,
        )

    run = ("-p", "hi", "--model", "fake/test", "--mode", "read-only")
    refused = edgar(*run)
    assert refused.returncode == 3 and "edgar trust" in refused.stderr
    assert edgar("trust", "--yes").returncode == 0
    listed = edgar("tools", "list").stdout
    assert "gh_issue" in listed and "service_status" in listed and "skill " in listed
    assert "changelog" in edgar("skills", "list").stdout
    assert edgar("skills", "validate").returncode == 0
    assert edgar(*run).returncode == 0


def test_j10_the_example_agent_from_the_docs(
    edgar_argv: list[str], subprocess_env: dict[str, str], tmp_project: Path
) -> None:
    # J10: once `.edgar/agents/code-reviewer.md` exists, `edgar tools list` shows
    # `task` on its own, exactly as examples/README.md claims [ROUTE-*, ADR-0053].
    examples = Path(__file__).resolve().parents[2] / "examples"
    (tmp_project / ".edgar" / "agents").mkdir(parents=True)
    shutil.copy(
        examples / "agents" / "code-reviewer.md",
        tmp_project / ".edgar" / "agents" / "code-reviewer.md",
    )
    listed = subprocess.run(
        [*edgar_argv, "tools", "list"],
        capture_output=True,
        text=True,
        env=subprocess_env,
        cwd=tmp_project,
    )
    assert listed.returncode == 0 and "task " in listed.stdout
