"""The commands that print what edgar would otherwise only do [CTX-2].

Each one prints something a turn would have used, and the test holds it to the
code that does the using: the rows of `edgar context show` must add up to the
builder's own count of the same prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from edgar.cli import admin
from edgar.cli.oneshot import run_prompt
from edgar.storage.transcript import find

ROW = re.compile(r"^\s*([\d,]+)\s{2}", re.MULTILINE)


def a_session(root: Path, home: Path) -> str:
    (root / ".edgar").mkdir(exist_ok=True)
    (root / ".edgar" / "config.toml").write_text('[model]\ndefault = "fake/test"\n')
    assert run_prompt("read a.txt", cwd=root, model=None, mode="ask", env={}, home=home) == 0
    return find(root, "").stem


def test_context_show_rows_add_up_to_the_builders_own_count(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from edgar.cli.setup import setup
    from edgar.config.load import load
    from edgar.context.builder import build, system_text
    from edgar.context.prompts import load_prompt
    from edgar.context.tokens import approx_message_tokens
    from edgar.storage.transcript import replay

    sid = a_session(tmp_project, home)
    capsys.readouterr()
    assert admin.command(["context", "show", sid], tmp_project, home) == 0
    out = capsys.readouterr().out
    counts = [int(n.replace(",", "")) for n in ROW.findall(out)]

    session, _ = replay(find(tmp_project, sid))
    s = setup(tmp_project, load(tmp_project, home=home), home=home)
    prompt = build(session, system_text(load_prompt(tmp_project).text, s.pinned))
    total = approx_message_tokens(prompt)
    assert counts[-1] == total  # the last row printed is the total
    assert sum(counts[:-1]) == total  # and the rows above it are that total, split up
    assert "cache breakpoint" in out and "system prompt" in out
    assert out.count("\n") == len(counts) + 2  # a header, the rows, the breakpoint


def test_sessions_compact_appends_to_the_record_and_keeps_the_pairing(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[CTX-10, CTX-4, CTX-14]"""
    from edgar.core.units import pairing_violations
    from edgar.storage.transcript import entries, replay

    sid = a_session(tmp_project, home)
    for n in range(7):
        assert (
            run_prompt(
                f"turn {n}", cwd=tmp_project, model=None, mode="ask", env={}, home=home, resume=sid
            )
            == 0
        )
    stored = replay(find(tmp_project, sid))[0]
    before = entries(find(tmp_project, sid))
    capsys.readouterr()

    assert admin.command(["sessions", "compact", sid], tmp_project, home) == 0
    assert "appended to the record" in capsys.readouterr().out
    after, _ = replay(find(tmp_project, sid))  # what --resume shows [CTX-14]
    assert pairing_violations(after.transcript) == []
    assert len(after.transcript) < len(stored.transcript)
    assert after.transcript[1].meta.get("via") == "summary"
    # Nothing was rewritten: every old line is still there, with the stages after them.
    now = entries(find(tmp_project, sid))
    assert now[: len(before)] == before and len(now) > len(before)
    assert now[len(before)]["type"] == "compaction"


def test_config_show_resolved_names_the_layer_and_never_prints_a_key(
    tmp_project: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """[CFG-2, CFG-6]"""
    (tmp_project / ".edgar").mkdir(exist_ok=True)
    project = tmp_project / ".edgar" / "config.toml"
    project.write_text(
        '[model]\ndefault = "fake/test"\n\n[permissions]\nmode = "ask"\n\n'
        '[providers.acme]\nkind = "openai-compatible"\nbase_url = "https://acme.test"\n'
        'api_key_env = "ACME_KEY"\n'
    )
    monkeypatch.setenv("ACME_KEY", "sk-do-not-print-me")
    monkeypatch.setenv("EDGAR_PERMISSIONS_MODE", "read-only")
    capsys.readouterr()

    assert admin.command(["config", "show", "--resolved"], tmp_project, home) == 0
    out = capsys.readouterr().out
    rows = {line.split()[0]: line for line in out.splitlines()}
    # The env var wins over the file, and the row says which layer it came from.
    assert "read-only" in rows["permissions.mode"]
    assert "env EDGAR_PERMISSIONS_MODE" in rows["permissions.mode"]
    assert str(project) in rows["model.default"] and "fake/test" in rows["model.default"]
    assert "default" in rows["context.keep_last_turns"]
    # The key is in the environment, never in the config, and never on screen.
    assert "sk-do-not-print-me" not in out
    assert "***" in rows["providers.acme.api_key"]
    assert "ACME_KEY" in rows["providers.acme.api_key_env"]
    assert admin.command(["config", "show"], tmp_project, home) == 0


def test_context_show_says_how_to_use_it_and_never_guesses_a_session(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.command(["context", "frobnicate"], tmp_project, home) == 2
    assert "usage: edgar context show" in capsys.readouterr().err


def test_route_explain_names_the_rule_that_decided_and_contacts_nothing(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[ROUTE-9] The rules are read in order, and the first match wins."""
    (tmp_project / ".edgar").mkdir(exist_ok=True)
    (tmp_project / ".edgar" / "config.toml").write_text(
        '[model]\ndefault = "fake/test"\ncompactor = "fake/small"\n\n'
        '[[route]]\nname = "long-prompts"\nmodel = "fake/big"\nprompt_tokens_gt = 10\n\n'
        '[[route]]\nname = "never-here"\nmodel = "fake/other"\nagent = "reviewer"\n'
    )
    capsys.readouterr()

    # A short prompt: no rule matches, so each role falls back to its own binding.
    assert admin.command(["route", "explain", "hi"], tmp_project, home) == 0
    rows = {line.split()[0]: line for line in capsys.readouterr().out.splitlines()}
    assert "fake/test" in rows["main"] and "default" in rows["main"]
    assert "fake/small" in rows["compactor"] and "[model] compactor" in rows["compactor"]

    # A long one crosses prompt_tokens_gt, and the row says which rule did it.
    assert admin.command(["route", "explain", "word " * 200], tmp_project, home) == 0
    out = capsys.readouterr().out
    rows = {line.split()[0]: line for line in out.splitlines()}
    assert "fake/big" in rows["main"] and "'long-prompts' matched" in rows["main"]
    assert "rule long-prompts" in out and "matched for role main" in out
    assert "rule never-here" in out and "skipped for role main" in out


def test_agents_list_and_validate_point_at_the_line_that_is_wrong(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[SUB-1, SUB-2] validate says file, line and reason; list says scope and model."""
    folder = tmp_project / ".edgar" / "agents"
    folder.mkdir(parents=True)
    (folder / "reviewer.md").write_text(
        '---\nname: reviewer\ndescription: reviews a diff\nmodel: "fake/big"\n---\nReview it.\n'
    )
    (folder / "broken.md").write_text(
        "---\nname: broken\ndescription: a bad one\nmode: sideways\n---\nGo.\n"
    )
    capsys.readouterr()

    assert admin.command(["agents", "list"], tmp_project, home) == 0
    out = capsys.readouterr().out
    assert "reviewer" in out and "project" in out and "fake/big" in out
    assert "broken" not in out  # it never loaded, so no session would see it

    assert admin.command(["agents", "validate"], tmp_project, home) == 1
    captured = capsys.readouterr()
    assert "1 agents ok, 1 with problems" in captured.out
    # The line number is the offending key's own line, not the file's first.
    assert f"{folder / 'broken.md'}:4: `mode` must be one of" in captured.err


def test_agents_says_how_to_use_it(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.command(["agents", "frobnicate"], tmp_project, home) == 2
    assert "usage: edgar agents list" in capsys.readouterr().err


def test_route_explain_says_how_to_use_it(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.command(["route", "frobnicate"], tmp_project, home) == 2
    assert "usage: edgar route explain" in capsys.readouterr().err


def labelled(out: str) -> dict[str, str]:
    # doctor prints "<check> <name> …": key each line by its first two words.
    return {" ".join(line.split()[:2]): line for line in out.splitlines()}


def test_doctor_checks_trust_the_db_mcp_and_extensions_without_touching_the_network(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[CFG-5] The whole run is offline: `no_network` fails the test on a socket."""
    (tmp_project / ".edgar").mkdir(exist_ok=True)
    (tmp_project / ".edgar" / "config.toml").write_text(
        '[model]\ndefault = "fake/test"\n\n'
        '[mcp.local]\ncommand = "definitely-not-a-real-program"\n\n'
        '[mcp.remote]\nurl = "https://mcp.example.test/mcp"\n'
    )
    bundle = tmp_project / ".edgar" / "extensions" / "demo"
    bundle.mkdir(parents=True)
    (bundle / "extension.toml").write_text(
        'name = "demo"\nversion = "0.1.0"\ndescription = "a demo"\n'
        '[requires]\ncommands = ["definitely-not-a-real-program"]\n'
    )
    capsys.readouterr()

    assert admin.command(["doctor"], tmp_project, home) == 0
    lines = labelled(capsys.readouterr().out)
    # An MCP server is executable config, so the project is untrusted until asked.
    assert "edgar trust" in lines["trust untrusted"]
    assert "not written yet" in lines["db project"]
    assert "not on PATH" in lines["mcp local"]
    assert "edgar mcp test remote" in lines["mcp remote"]
    assert "not on PATH" in lines["ext demo"]
    # Nothing was asked of any endpoint; the line says how to ask.
    assert "--network" in lines["conn (skipped)"]


def test_doctor_reports_a_real_database_as_sound(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from edgar.storage.db import Store

    Store(tmp_project / ".edgar" / "edgar.db").grant("read", "a.txt")  # a session's own file
    capsys.readouterr()
    assert admin.command(["doctor"], tmp_project, home) == 0
    assert "db       project     integrity_check ok" in capsys.readouterr().out
