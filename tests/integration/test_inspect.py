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
