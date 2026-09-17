"""`edgar controller log|apply|revert`: the three things a person does with the
mutation log [CTRL-7, CTRL-10]."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.controller.apply import Site, apply
from edgar.controller.cli import command
from edgar.controller.proposals import Compact, TightenPolicy
from edgar.controller.store import Controls
from edgar.controller.tighten import Narrowing
from edgar.permissions.policy import Policy


def _site(tmp_path: Path, *, dry_run: bool = True) -> Site:
    policy = Policy(mode="auto", cwd=tmp_path, home=tmp_path)
    return Site(Controls(tmp_path / ".edgar" / "controller.db"), tmp_path, policy, dry_run)


def test_a_project_that_never_ran_the_controller_says_so_and_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["controller", "log"], tmp_path) == 0
    assert "has not done anything" in capsys.readouterr().out


def test_the_log_shows_the_id_the_state_and_the_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path)
    outcome = apply(Compact(0.5, "the window was filling"), site)
    assert command(["controller", "log"], tmp_path) == 0
    printed = capsys.readouterr().out
    assert f"{outcome.mutation_id:>4}" in printed
    assert "proposed" in printed
    assert "because: the window was filling" in printed


def test_a_refusal_is_in_the_log_too_because_that_is_where_you_would_look(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A controller refused every turn is a configuration problem, and silence about
    # it is the failure mode worth avoiding [CTRL-8].
    apply(TightenPolicy(Narrowing(mode="yolo"), "let me work"), _site(tmp_path))
    assert command(["controller", "log"], tmp_path) == 0
    printed = capsys.readouterr().out
    assert "refused" in printed and "looser" in printed


def test_apply_by_id_is_what_turns_a_dry_run_into_the_real_thing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path)
    outcome = apply(Compact(0.45, "why"), site)
    assert site.store.overrides() == {}
    assert command(["controller", "apply", str(outcome.mutation_id)], tmp_path) == 0
    assert "applied" in capsys.readouterr().out
    assert site.store.overrides() == {"compact": "0.4500"}


def test_revert_by_id_takes_it_back_out(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    site = _site(tmp_path, dry_run=False)
    outcome = apply(Compact(0.45, "why"), site)
    assert command(["controller", "revert", str(outcome.mutation_id)], tmp_path) == 0
    assert "reverted" in capsys.readouterr().out
    assert site.store.overrides() == {}


def test_an_id_that_is_not_there_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["controller", "revert", "9"], tmp_path) == 2
    assert "no mutation 9" in capsys.readouterr().out


def test_an_id_that_is_not_a_number_says_where_to_find_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["controller", "revert", "latest"], tmp_path) == 2
    assert "controller log" in capsys.readouterr().err


def test_an_unknown_subcommand_prints_the_usage_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # There is deliberately no `edgar controller run`: the gate is the only thing
    # that starts a call, and a threshold is the only thing that asks it to [CTRL-2].
    assert command(["controller", "run"], tmp_path) == 2
    assert "usage: edgar controller log" in capsys.readouterr().err
