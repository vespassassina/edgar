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


def test_context_show_says_how_to_use_it_and_never_guesses_a_session(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.command(["context", "frobnicate"], tmp_project, home) == 2
    assert "usage: edgar context show" in capsys.readouterr().err
