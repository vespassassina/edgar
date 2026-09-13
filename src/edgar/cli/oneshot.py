"""`edgar -p`: one turn, non-interactive [CLI-2, CLI-3, CLI-7, CLI-18].

Only the result goes to stdout [CLI-5]: the final text, or with `--json` one
object, or with `--events` the event stream as JSON Lines. The status line goes to
stderr, and only when stderr is a terminal [CLI-6]. Piped stdin is attached
context, never the prompt [CLI-3].
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from edgar.cli import trust
from edgar.cli.render import event_line
from edgar.cli.setup import authorise_verify, begin, finish, prepare, setup
from edgar.cli.statusbar import Status, StderrLine, terminal_ready
from edgar.core.errors import ConfigError
from edgar.core.events import Event, EventBus, Subscriber, ThinkingDelta, ToolStarted, TurnFinished
from edgar.core.loop import Runtime, TurnResult, run_turn
from edgar.core.session import Session

Output = Literal["text", "json", "events"]


def run_prompt(
    prompt: str,
    *,
    cwd: Path | None,
    model: str | None,
    mode: str | None,
    subscribers: Iterable[Subscriber] = (),
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    output: Output = "text",
    quiet: bool = False,
    show_thinking: bool = False,
    attached: str | None = None,
    verify: str | None = None,
    project_exec: bool = True,
    resume: str | None = None,
) -> int:
    if mode is None:
        # Nobody is there to answer a permission prompt, so the mode must be a
        # decision the caller made, not a default [CLI-9, ADR-0004].
        raise ConfigError(
            "non-interactive runs need an explicit --mode",
            hint="add --mode read-only to look, or --mode ask|auto|yolo",
        )
    root, config = prepare(cwd, model=model, mode=mode, env=env, home=home)
    if project_exec:
        trust.require(root, config, home or Path.home())  # untrusted: exit 3 [PERM-13]
    s = setup(root, config, home=home, env=env, verify=verify, project_exec=project_exec)
    for warning in s.warnings:
        print(f"edgar: {warning}", file=sys.stderr)
    bus = EventBus()
    for subscriber in subscribers:
        bus.subscribe(subscriber)
    tools: list[str] = []
    finished: list[TurnFinished] = []
    bus.subscribe(lambda e: _track(e, tools, finished))
    if output == "events":
        bus.subscribe(lambda e: _emit(e, show_thinking))
    elif show_thinking:
        bus.subscribe(_thinking_to_stderr)
    status = None
    if not quiet and terminal_ready(sys.stderr):
        status = Status(config.model.default or "")
        bus.subscribe(status)
    session, rt = begin(s, bus, resume)
    if session.log is not None:
        bus.subscribe(session.log.event)  # the audit trail and the turn's cost [PERM-10]
    try:
        result = asyncio.run(_run(session, prompt, rt, [attached] if attached else [], status))
    finally:
        finish(s, session)
    codes = {"verification_failed": 9, "budget_exceeded": 6}
    code = codes.get(result.reason, 5 if s.guard.prompt_denials else 0)

    if output == "json":
        done = finished[-1]
        payload = {
            "result": result.text,
            "usage": asdict(result.usage),
            "cost": done.cost,
            "tools": tools,
            "reason": result.reason,  # exit 9 for verification_failed, 6 for budget_exceeded
            "model": rt.name,
            "session": session.id,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    elif output == "text":
        sys.stdout.write(result.text if result.text.endswith("\n") else result.text + "\n")
    if code == 5:  # an Ask with nobody to answer is a denial, and the run says so [PERM-7]
        print("edgar: a tool call needed permission; see --mode or [permissions]", file=sys.stderr)
    elif code == 9:
        print("edgar: the verify command still fails; out of attempts", file=sys.stderr)
    elif code == 6:  # the partial result went to stdout above [BUD-3]
        print("edgar: a cost cap was reached; the result is partial", file=sys.stderr)
    return code


async def _run(
    session: Session, prompt: str, rt: Runtime, attached: list[str], status: Status | None
) -> TurnResult:
    line = StderrLine(status) if status else None
    ticker = asyncio.create_task(line.run()) if line else None
    try:
        await authorise_verify(rt, session)
        return await run_turn(session, prompt, rt, attached=attached)
    finally:
        if ticker and line:
            ticker.cancel()
            line.clear()


def _track(event: Event, tools: list[str], finished: list[TurnFinished]) -> None:
    if isinstance(event, ToolStarted):
        tools.append(event.tool)
    elif isinstance(event, TurnFinished):
        finished.append(event)


def _emit(event: Event, show_thinking: bool) -> None:
    if isinstance(event, ThinkingDelta) and not show_thinking:
        return  # reasoning is included only when asked for [CLI-21]
    sys.stdout.write(event_line(event) + "\n")
    sys.stdout.flush()


def _thinking_to_stderr(event: Event) -> None:
    if isinstance(event, ThinkingDelta):
        sys.stderr.write(event.text)
        sys.stderr.flush()
