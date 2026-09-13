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


def test_loop_is_budgeted_in_physical_lines(tmp_path: Path) -> None:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "loop.py").write_text("\n" * 201)
    loop = next(lim for lim in limits(tmp_path) if lim.label.startswith("core/loop.py"))
    assert not loop.ok


def test_v2_tier_also_checks_the_v1_remainder(tmp_path: Path) -> None:
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "learner.py").write_text("x = 1\n")
    (tmp_path / "cli.py").write_text("y = 2\n")
    remainder = next(lim for lim in limits(tmp_path, "v2") if "without v2" in lim.label)
    assert remainder.loc == 1
