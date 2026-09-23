"""The self_schedules table [SCH-11]: it lives beside grants and trust in the
project's edgar.db, never in schedules.toml."""

from __future__ import annotations

from pathlib import Path

from edgar.schedule.store import SelfSchedules


def _store(tmp_path: Path) -> SelfSchedules:
    return SelfSchedules(tmp_path / "edgar.db")


def test_a_fresh_store_has_nothing_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.list() == []
    assert store.pending_count() == 0
    assert store.created_since(86400) == 0


def test_add_then_list_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = store.add(
        name="nightly",
        when="@daily",
        prompt="Summarise.",
        mode="read-only",
        allowlist=("read", "fetch"),
        scope=("paths=reports/",),
        catch_up="once",
        depth=1,
    )
    assert entry.name == "nightly" and entry.mode == "read-only"
    (row,) = store.list()
    assert row.entry.name == "nightly"
    assert row.entry.allowlist == ("read", "fetch")
    assert row.entry.scope == ("paths=reports/",)
    assert row.depth == 1
    assert store.pending_count() == 1
    assert store.created_since(86400) == 1


def test_remove_drops_the_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add(
        name="a",
        when="@daily",
        prompt="p",
        mode="read-only",
        allowlist=(),
        scope=(),
        catch_up="once",
        depth=0,
    )
    assert store.remove("a") is True
    assert store.list() == []
    assert store.remove("a") is False


def test_created_since_ignores_rows_older_than_the_window(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import time

    store = _store(tmp_path)
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    store.add(
        name="old",
        when="@daily",
        prompt="p",
        mode="read-only",
        allowlist=(),
        scope=(),
        catch_up="once",
        depth=0,
    )
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0 + 90000)
    assert store.created_since(86400) == 0
    assert store.pending_count() == 1
