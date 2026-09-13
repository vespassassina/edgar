from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from edgar.core.events import EventBus
from edgar.tools.base import ToolContext, ToolResult
from edgar.tools.builtin.fs import LS_LIMIT, Ls, Read


def _read(root: Path, **args: Any) -> ToolResult:
    ctx = ToolContext(cwd=root, bus=EventBus(), blob_dir=root, max_output_tokens=8000)
    return asyncio.run(Read().run(args, ctx))


def _ls(root: Path, **args: Any) -> ToolResult:
    ctx = ToolContext(cwd=root, bus=EventBus(), blob_dir=root, max_output_tokens=8000)
    return asyncio.run(Ls().run(args, ctx))


def test_read_numbers_lines(tmp_project: Path) -> None:
    assert _read(tmp_project, path="a.txt").text == "     1\thello\n     2\tworld"


def test_read_window_says_how_to_continue(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("\n".join(f"line {i}" for i in range(1, 11)))
    out = _read(tmp_path, path="f.txt", offset=3, limit=2).text
    assert out.splitlines()[:2] == ["     3\tline 3", "     4\tline 4"]
    assert "[6 more lines; continue with offset=5]" in out


def test_read_failures_are_typed(tmp_project: Path) -> None:
    (tmp_project / "bin.dat").write_bytes(b"\x00\x01\x02")
    (tmp_project / "empty.txt").write_text("")
    assert _read(tmp_project, path="missing").error == "not_found"
    assert _read(tmp_project, path="src").error == "validation"
    assert _read(tmp_project, path="bin.dat").error == "validation"
    assert _read(tmp_project, path="empty.txt") == ToolResult("empty.txt is empty")


def test_read_keeps_going_past_bad_utf8(tmp_path: Path) -> None:
    (tmp_path / "latin1.txt").write_bytes("café".encode("latin-1"))
    assert _read(tmp_path, path="latin1.txt").error is None


def test_ls_marks_directories_and_sorts(tmp_project: Path) -> None:
    assert _ls(tmp_project).text == "a.txt\nsrc/"
    assert _ls(tmp_project, path="src").text == "(empty)"


def test_ls_failures(tmp_project: Path) -> None:
    assert _ls(tmp_project, path="missing").error == "not_found"
    assert _ls(tmp_project, path="a.txt").error == "validation"


def test_ls_caps_long_listings(tmp_path: Path) -> None:
    for i in range(LS_LIMIT + 5):
        (tmp_path / f"f{i:05}").touch()
    assert _ls(tmp_path).text.endswith("[5 more entries not shown]")
