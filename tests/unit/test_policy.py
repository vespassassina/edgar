"""The M1 policy: reads inside the working directory, nothing else. The full engine
and its hostile-path property tests arrive in M3."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.permissions.policy import Allow, Deny, decide
from edgar.tools.base import ToolSchema
from edgar.tools.builtin.fs import Read


def _write_tool() -> ToolSchema:
    return ToolSchema("write", "", {}, kind="builtin", origin="builtin", category="write")


@pytest.mark.parametrize("path", ["a.txt", "src/../a.txt", ".", "./src"])
def test_reads_inside_are_allowed(tmp_project: Path, path: str) -> None:
    assert decide(Read.schema, {"path": path}, mode="read-only", cwd=tmp_project) == Allow()


@pytest.mark.parametrize("path", ["..", "../x", "src/../../x", "/etc/passwd"])
def test_reads_outside_are_denied(tmp_project: Path, path: str) -> None:
    assert isinstance(decide(Read.schema, {"path": path}, mode="yolo", cwd=tmp_project), Deny)


def test_a_symlink_that_leaves_the_root_is_judged_by_its_target(
    tmp_project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    link = tmp_project / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:  # Windows without developer mode cannot create symlinks
        return
    assert isinstance(decide(Read.schema, {"path": "link.txt"}, mode="ask", cwd=tmp_project), Deny)


def test_non_read_tools_are_denied_in_every_mode(tmp_project: Path) -> None:
    for mode in ("read-only", "ask", "auto", "yolo"):
        assert isinstance(decide(_write_tool(), {}, mode=mode, cwd=tmp_project), Deny)
