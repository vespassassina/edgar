"""Size budgets [NFR-4, ADR-0015]. If one fails, something moves to a later tier."""

from __future__ import annotations

from pathlib import Path

import pytest
from budget import Limit, count_loc, limits


@pytest.mark.parametrize("limit", limits(), ids=lambda limit: limit.label)
def test_within_budget(limit: Limit) -> None:
    assert limit.ok, limit


def test_blank_lines_and_comments_do_not_count(tmp_path: Path) -> None:
    source = tmp_path / "m.py"
    source.write_text('"""Doc."""\n\n# note\nx = 1  # trailing\n    # indented\n')
    assert count_loc(source) == 2


def _loop_limit(root: Path, source: str) -> Limit:
    # Write a fake core/loop.py and return the loop's budget line for it.
    (root / "core").mkdir()
    (root / "core" / "loop.py").write_text(source)
    return next(lim for lim in limits(root) if lim.label.startswith("core/loop.py"))


def test_the_loop_is_budgeted_in_lines_of_code(tmp_path: Path) -> None:
    # 201 lines of code: over the loop's 200 [ADR-0040].
    assert not _loop_limit(tmp_path, "x = 1\n" * 201).ok


def test_comments_in_the_loop_are_free(tmp_path: Path) -> None:
    # 200 lines of code plus 300 lines of comments and blanks: still within budget.
    source = "# step\n\n" * 150 + "x = 1\n" * 200
    assert _loop_limit(tmp_path, source).ok


def test_removable_tiers_also_check_the_remainder(tmp_path: Path) -> None:
    # v3 and v4 are removable [NFR-12, ADR-0057]: what is left without them must
    # still fit v2's budget, and the count excludes only the removable packages.
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "learner.py").write_text("x = 1\n")
    (tmp_path / "cli.py").write_text("y = 2\n")
    remainder = next(lim for lim in limits(tmp_path, "v3") if "without removable" in lim.label)
    assert remainder.loc == 1
    assert not any("without removable" in lim.label for lim in limits(tmp_path, "v2"))
