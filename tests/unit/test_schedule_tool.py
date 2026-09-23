"""schedule_self [SCH-11]: a run scheduling its own future run never gets more
authority than it already has, and its nesting, pending count and rate are capped."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from edgar.broker.caveats import parse_scope
from edgar.broker.guard import TicketGuard
from edgar.broker.ticket import Ticket
from edgar.core.events import EventBus
from edgar.schedule.store import MAX_DEPTH, MAX_PENDING, MAX_PER_DAY, SelfSchedules
from edgar.schedule.tool import ScheduleSelfTool
from edgar.tools.base import ToolContext


def _ctx(tmp_path: Path, *, mode: str = "auto", broker: TicketGuard | None = None) -> ToolContext:
    return ToolContext(
        cwd=tmp_path,
        bus=EventBus(),
        blob_dir=tmp_path / "blobs",
        max_output_tokens=8000,
        mode=mode,
        broker=broker,
    )


def _tool(tmp_path: Path, depth: int = 0) -> ScheduleSelfTool:
    return ScheduleSelfTool(SelfSchedules(tmp_path / "edgar.db"), depth)


def test_a_valid_call_is_stored_and_reported(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    result = asyncio.run(
        tool.run({"name": "nightly", "when": "@daily", "prompt": "Summarise."}, _ctx(tmp_path))
    )
    assert not result.error and "nightly" in result.text
    assert tool.store.pending_count() == 1


def test_mode_never_widens_past_the_callers_mode(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    asyncio.run(
        tool.run(
            {"name": "a", "when": "@daily", "prompt": "p", "mode": "yolo"},
            _ctx(tmp_path, mode="ask"),
        )
    )
    (row,) = tool.store.list()
    assert row.entry.mode == "ask"


def test_a_bad_when_expression_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    result = asyncio.run(tool.run({"name": "a", "when": "nonsense", "prompt": "p"}, _ctx(tmp_path)))
    assert result.error == "validation"
    assert tool.store.pending_count() == 0


def test_depth_past_the_ceiling_is_refused(tmp_path: Path) -> None:
    tool = _tool(tmp_path, depth=MAX_DEPTH)
    result = asyncio.run(tool.run({"name": "a", "when": "@daily", "prompt": "p"}, _ctx(tmp_path)))
    assert result.error == "permission_denied"
    assert tool.store.pending_count() == 0


def test_the_pending_cap_refuses_a_new_entry(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    for i in range(MAX_PENDING):
        tool.store.add(
            name=f"e{i}",
            when="@daily",
            prompt="p",
            mode="ask",
            allowlist=(),
            scope=(),
            catch_up="once",
            depth=0,
        )
    result = asyncio.run(
        tool.run({"name": "one_more", "when": "@daily", "prompt": "p"}, _ctx(tmp_path))
    )
    assert result.error == "permission_denied"


def test_the_daily_rate_limit_refuses_a_new_entry(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    for i in range(MAX_PER_DAY):
        tool.store.add(
            name=f"e{i}",
            when="@daily",
            prompt="p",
            mode="ask",
            allowlist=(),
            scope=(),
            catch_up="once",
            depth=0,
        )
    for i in range(MAX_PER_DAY):
        tool.store.remove(f"e{i}")  # pending count clears, the day's rate does not
    result = asyncio.run(
        tool.run({"name": "one_more", "when": "@daily", "prompt": "p"}, _ctx(tmp_path))
    )
    assert result.error == "permission_denied"


def test_scope_and_allowlist_attenuate_a_live_ticket(tmp_path: Path) -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=a.txt"]))
    tool = _tool(tmp_path)
    asyncio.run(
        tool.run(
            {"name": "a", "when": "@daily", "prompt": "p", "allowlist": ["read"]},
            _ctx(tmp_path, broker=TicketGuard(ticket)),
        )
    )
    (row,) = tool.store.list()
    assert "paths=a.txt" in row.entry.scope  # the parent's caveat still holds [CAP-5]
    assert row.entry.allowlist == ("read",)


def test_with_no_broker_the_raw_scope_and_allowlist_are_kept(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    asyncio.run(
        tool.run(
            {"name": "a", "when": "@daily", "prompt": "p", "scope": ["paths=x"]},
            _ctx(tmp_path, broker=None),
        )
    )
    (row,) = tool.store.list()
    assert row.entry.scope == ("paths=x",)


@pytest.mark.parametrize("depth", [0, 1, MAX_DEPTH - 1])
def test_a_stored_entry_records_one_deeper_than_the_caller(tmp_path: Path, depth: int) -> None:
    tool = _tool(tmp_path, depth=depth)
    asyncio.run(tool.run({"name": "a", "when": "@daily", "prompt": "p"}, _ctx(tmp_path)))
    (row,) = tool.store.list()
    assert row.depth == depth + 1
