"""schedules.toml -> ScheduleEntry [SCH-1, SCH-8]."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.core.errors import ConfigError
from edgar.schedule.due import Cron, Interval
from edgar.schedule.parser import append, load, path, remove


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


def test_append_adds_an_entry_without_touching_what_was_already_there(tmp_path: Path) -> None:
    _write(tmp_path, '[[entries]]\nname = "old"\nwhen = "@daily"\nprompt = "keep me"\n')
    original = path(tmp_path).read_text(encoding="utf-8")
    append(tmp_path, {"name": "new", "when": "@hourly", "prompt": "the new one"})
    assert path(tmp_path).read_text(encoding="utf-8").startswith(original)
    names = [e.name for e in load(tmp_path)]
    assert names == ["old", "new"]


def test_append_validates_before_writing_anything(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        append(tmp_path, {"name": "bad", "when": "nonsense", "prompt": "x"})
    assert not path(tmp_path).exists()


def test_append_round_trips_scope_and_allowlist(tmp_path: Path) -> None:
    append(
        tmp_path,
        {
            "name": "backup",
            "when": "every 15m",
            "prompt": "back it up",
            "allowlist": ["read", "fetch"],
            "scope": {"paths": "reports/"},
        },
    )
    (entry,) = load(tmp_path)
    assert entry.allowlist == ("read", "fetch")
    assert entry.scope == ("paths=reports/",)


def test_remove_drops_the_named_entry_and_keeps_the_rest(tmp_path: Path) -> None:
    append(tmp_path, {"name": "a", "when": "@daily", "prompt": "a"})
    append(tmp_path, {"name": "b", "when": "@daily", "prompt": "b"})
    assert remove(tmp_path, "a") is True
    assert [e.name for e in load(tmp_path)] == ["b"]


def test_remove_reports_false_for_an_unknown_name(tmp_path: Path) -> None:
    append(tmp_path, {"name": "a", "when": "@daily", "prompt": "a"})
    assert remove(tmp_path, "nonexistent") is False


def test_remove_with_no_file_at_all_reports_false(tmp_path: Path) -> None:
    assert remove(tmp_path, "anything") is False
