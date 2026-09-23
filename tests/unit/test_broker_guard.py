"""The ticket's own veto, one step before the permission engine [CAP-3, CAP-6]."""

from __future__ import annotations

import asyncio
from pathlib import Path

from harness import Recorder, guard, tool_use

from edgar.broker.caveats import parse_scope
from edgar.broker.guard import TicketGuard
from edgar.broker.ticket import Ticket
from edgar.core.events import EventBus, ScopeRefused
from edgar.core.message import ToolResultBlock
from edgar.permissions.matcher import Subject
from edgar.tools.base import ToolContext
from edgar.tools.execute import execute
from edgar.tools.registry import core_registry


def _ctx(
    root: Path, ticket_guard: TicketGuard | None, recorder: Recorder | None = None
) -> ToolContext:
    bus = EventBus()
    if recorder is not None:
        bus.subscribe(recorder)
    return ToolContext(
        cwd=root,
        bus=bus,
        blob_dir=root / ".edgar" / "blobs",
        max_output_tokens=8000,
        broker=ticket_guard,
    )


def _run(ctx: ToolContext, root: Path, args: dict[str, object]) -> ToolResultBlock:
    gate = guard(root, "read-only")
    return asyncio.run(
        execute(
            tool_use("read", args), registry=core_registry(), ctx=ctx, guard=gate, mode="read-only"
        )
    )


def test_no_broker_on_the_context_refuses_nothing(tmp_project: Path) -> None:
    result = _run(_ctx(tmp_project, None), tmp_project, {"path": "a.txt"})
    assert not result.is_error


def test_a_call_inside_the_paths_caveat_is_allowed(tmp_project: Path) -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=a.txt"]))
    result = _run(_ctx(tmp_project, TicketGuard(ticket)), tmp_project, {"path": "a.txt"})
    assert not result.is_error


def test_a_call_outside_the_paths_caveat_is_refused(tmp_project: Path, recorder: Recorder) -> None:
    (tmp_project / "src" / "b.txt").write_text("other\n", encoding="utf-8")
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=a.txt"]))
    ctx = _ctx(tmp_project, TicketGuard(ticket), recorder)
    result = _run(ctx, tmp_project, {"path": "src/b.txt"})
    assert result.is_error and result.error and result.error.kind == "out_of_scope"
    (refused,) = recorder.of(ScopeRefused)
    assert refused.caveat == "paths" and refused.tool == "read"


def test_a_refused_call_does_not_count_toward_the_calls_cap(tmp_project: Path) -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=a.txt", "calls=1"]))
    ticket_guard = TicketGuard(ticket)
    ctx = _ctx(tmp_project, ticket_guard)
    _run(ctx, tmp_project, {"path": "src/missing.txt"})  # refused by paths, not counted
    result = _run(ctx, tmp_project, {"path": "a.txt"})  # still the ticket's first real call
    assert not result.is_error
    assert ticket_guard.calls_so_far == 1


def test_the_calls_cap_refuses_once_reached(tmp_project: Path) -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["calls=1"]))
    ticket_guard = TicketGuard(ticket)
    ctx = _ctx(tmp_project, ticket_guard)
    first = _run(ctx, tmp_project, {"path": "a.txt"})
    second = _run(ctx, tmp_project, {"path": "a.txt"})
    assert not first.is_error
    assert second.is_error and second.error and second.error.kind == "out_of_scope"


def test_narrowed_adds_a_tools_caveat_from_the_agent_definition() -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=a.txt"]))
    child = TicketGuard(ticket).narrowed(subject="task:helper#s1", tools=("read",), scope=())
    by_kind = {c.kind: c.value for c in child.ticket.caveats}
    assert by_kind["tools"] == "read"
    assert by_kind["paths"] == "a.txt"  # the parent's caveat still holds
    assert child.ticket.subject == "task:helper#s1"
    assert child.ticket.parent is ticket


def test_narrowed_merges_in_the_model_given_scope() -> None:
    ticket = Ticket(intent_id="i1")
    child = TicketGuard(ticket).narrowed(subject="task:helper#s1", tools=(), scope=("paths=a.txt",))
    by_kind = {c.kind: c.value for c in child.ticket.caveats}
    assert by_kind["paths"] == "a.txt"


def test_ticket_guard_check_matches_the_subject_it_is_given(tmp_project: Path) -> None:
    ticket = Ticket(intent_id="i1", caveats=parse_scope(["hosts=api.github.com"]))
    ticket_guard = TicketGuard(ticket)
    refused = ticket_guard.check(
        tool="fetch", read_only=True, subject=Subject("https://evil.example/x"), cwd=tmp_project
    )
    assert refused is not None and refused[0] == "hosts"
