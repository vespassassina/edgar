"""Helpers for driving the loop in tests with the fake provider."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripted import ScriptedProvider, ScriptedResponse

from edgar.core.events import Event, EventBus
from edgar.core.loop import Runtime, TurnResult, run_turn
from edgar.core.message import ToolUseBlock
from edgar.core.session import Session
from edgar.permissions.guard import Asker, Guard
from edgar.permissions.policy import Policy
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.registry import ToolRegistry, core_registry


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        return [e.name for e in self.events]

    def of(self, kind: type[Event]) -> list[Any]:
        return [e for e in self.events if isinstance(e, kind)]


def guard(cwd: Path, mode: str = "read-only", asker: Asker | None = None) -> Guard:
    """The permission guard with config defaults; `asker` answers any Ask."""
    return Guard(Policy(mode=mode, cwd=cwd, home=cwd.parent / "home"), asker=asker)


def tool_use(name: str, args: dict[str, Any], id: str | None = None) -> ToolUseBlock:
    return ToolUseBlock(id or f"tu_{name}", name, args)


def runtime(
    provider: ScriptedProvider,
    recorder: Recorder | None = None,
    *,
    tools: ToolRegistry | None = None,
    max_output_tokens: int = 8000,
    name: str = "",
    fallback: tuple[tuple[str, Any, str], ...] = (),
    escalation: Any | None = None,
) -> Runtime:
    bus = EventBus()
    if recorder is not None:
        bus.subscribe(recorder)
    return Runtime(
        provider=provider,
        model="test",
        tools=tools or core_registry(),
        system_prompt="system prompt",
        bus=bus,
        max_output_tokens=max_output_tokens,
        name=name,
        fallback=fallback,
        escalation=escalation,
    )


def run_turn_sync(session: Session, prompt: str, rt: Runtime) -> TurnResult:
    return asyncio.run(run_turn(session, prompt, rt))


def scripted(*steps: ScriptedResponse) -> ScriptedProvider:
    return ScriptedProvider(list(steps))


def new_session(cwd: Path, mode: str = "read-only") -> Session:
    return Session(cwd=cwd, model="fake/test", mode=mode)


def texts(steps: Sequence[str]) -> list[ScriptedResponse]:
    return [ScriptedResponse(text=t) for t in steps]


class SlowTool:
    """A read-only tool that takes `seconds` to answer: something to cancel mid-call."""

    schema = ToolSchema(
        name="slow",
        description="Wait, then answer.",
        input_schema={"type": "object", "properties": {"seconds": {"type": "number"}}},
        kind="builtin",
        origin="builtin",
        category="read",
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(float(args.get("seconds", 0.05)))
        return ToolResult("slept")


def slow_registry() -> ToolRegistry:
    from edgar.tools.builtin.fs import builtins

    return ToolRegistry([*builtins(), SlowTool()])
