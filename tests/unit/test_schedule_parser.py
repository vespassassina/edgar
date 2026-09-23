"""schedules.toml -> ScheduleEntry [SCH-1, SCH-8]."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.core.errors import ConfigError
from edgar.schedule.due import Cron, Interval
from edgar.schedule.parser import load, path


def _write(cwd: Path, text: str) -> None:
    path(cwd).parent.mkdir(parents=True, exist_ok=True)
    path(cwd).write_text(text, encoding="utf-8")


def test_no_file_is_no_entries_not_an_error(tmp_path: Path) -> None:
    assert load(tmp_path) == ()


def test_a_minimal_entry_gets_its_defaults(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        [[entries]]
        name = "nightly"
        when = "@daily"
        prompt = "Summarise the day."
        """,
    )
    (entry,) = load(tmp_path)
    assert entry.name == "nightly"
    assert isinstance(entry.when, Cron)
    assert entry.mode == "read-only"
    assert entry.catch_up == "once"
    assert entry.allowlist == ()
    assert entry.scope == ()


def test_every_field_is_read_when_present(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        [[entries]]
        name = "backup"
        when = "every 15m"
        prompt = "Back up the reports folder."
        mode = "auto"
        agent = "backup-agent"
        model = "gpt-5-mini"
        allowlist = ["read", "fetch"]
        verify = "just check"
        catch_up = "all"

        [entries.scope]
        paths = "reports/"
        """,
    )
    (entry,) = load(tmp_path)
    assert entry.when == Interval(900)
    assert entry.mode == "auto"
    assert entry.agent == "backup-agent"
    assert entry.model == "gpt-5-mini"
    assert entry.allowlist == ("read", "fetch")
    assert entry.verify == "just check"
    assert entry.catch_up == "all"
    assert entry.scope == ("paths=reports/",)


def test_two_entries_load_in_file_order(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        [[entries]]
        name = "first"
        when = "@hourly"
        prompt = "a"

        [[entries]]
        name = "second"
        when = "@daily"
        prompt = "b"
        """,
    )
    entries = load(tmp_path)
    assert [e.name for e in entries] == ["first", "second"]


def test_a_missing_required_field_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, '[[entries]]\nname = "nightly"\nwhen = "@daily"\n')
    with pytest.raises(ConfigError, match="prompt"):
        load(tmp_path)


def test_an_unknown_mode_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        '[[entries]]\nname = "n"\nwhen = "@daily"\nprompt = "p"\nmode = "god-mode"\n',
    )
    with pytest.raises(ConfigError, match="mode"):
        load(tmp_path)


def test_an_unknown_catch_up_policy_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        '[[entries]]\nname = "n"\nwhen = "@daily"\nprompt = "p"\ncatch_up = "eventually"\n',
    )
    with pytest.raises(ConfigError, match="catch_up"):
        load(tmp_path)


def test_a_bad_when_expression_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, '[[entries]]\nname = "n"\nwhen = "whenever"\nprompt = "p"\n')
    with pytest.raises(ConfigError):
        load(tmp_path)


def test_malformed_toml_is_a_config_error_not_a_traceback(tmp_path: Path) -> None:
    _write(tmp_path, "this is not [ toml")
    with pytest.raises(ConfigError):
        load(tmp_path)
