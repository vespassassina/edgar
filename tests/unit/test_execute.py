"""The tool pipeline: every failure comes back to the model, none raises [TOOL-2..4]."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from harness import Recorder, guard, tool_use

from edgar.core.events import EventBus, ToolFinished
from edgar.core.message import ToolResultBlock, ToolUseBlock
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.execute import _fan_out_group, execute, execute_many
from edgar.tools.registry import ToolRegistry, core_registry


def _ctx(root: Path, recorder: Recorder | None = None, **kw: Any) -> ToolContext:
    bus = EventBus()
    if recorder is not None:
        bus.subscribe(recorder)
    defaults: dict[str, Any] = {"blob_dir": root / ".edgar" / "blobs", "max_output_tokens": 8000}
    return ToolContext(cwd=root, bus=bus, **(defaults | kw))


def _run(
    call: ToolUseBlock, ctx: ToolContext, registry: ToolRegistry | None = None
) -> ToolResultBlock:
    registry = registry or core_registry()
    gate = guard(ctx.cwd, "read-only")
    return asyncio.run(execute(call, registry=registry, ctx=ctx, guard=gate, mode="read-only"))


class _Stub:
    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour
        self.schema = ToolSchema(
            name="stub",
            description="test tool",
            input_schema={"type": "object"},
            kind="builtin",
            origin="builtin",
            category="read",
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if self.behaviour == "slow":
            await asyncio.sleep(10)
        if self.behaviour == "crash":
            raise RuntimeError("boom")
        return ToolResult("x" * 1000)


def test_unknown_tool(tmp_project: Path) -> None:
    result = _run(tool_use("nope", {}), _ctx(tmp_project))
    assert result.is_error and result.error and result.error.kind == "not_found"
    assert "read" in result.text


def test_invalid_arguments_are_reported_not_raised(tmp_project: Path) -> None:
    result = _run(tool_use("read", {"path": 3, "extra": True}), _ctx(tmp_project))
    assert result.is_error and result.error and result.error.kind == "validation"
    assert "path" in result.text and "extra" in result.text


def test_missing_required_argument(tmp_project: Path) -> None:
    result = _run(tool_use("read", {}), _ctx(tmp_project))
    assert result.error and result.error.kind == "validation"
    assert "'path' is a required property" in result.text


def test_timeout(tmp_project: Path, recorder: Recorder) -> None:
    ctx = _ctx(tmp_project, recorder, timeout_s=0.05)
    result = _run(tool_use("stub", {}), ctx, ToolRegistry([_Stub("slow")]))
    assert result.error and result.error.kind == "timeout"
    assert recorder.names[-1] == "ToolFinished"


def test_a_crashing_tool_becomes_an_internal_error(tmp_project: Path) -> None:
    result = _run(tool_use("stub", {}), _ctx(tmp_project), ToolRegistry([_Stub("crash")]))
    assert result.error and result.error.kind == "internal"
    assert "RuntimeError: boom" in result.text


def test_large_output_is_spilled_with_head_tail_and_blob(
    tmp_project: Path, recorder: Recorder
) -> None:
    ctx = _ctx(tmp_project, recorder, max_output_tokens=50)
    result = _run(tool_use("stub", {}, id="tu/7"), ctx, ToolRegistry([_Stub("big")]))
    assert result.truncated and result.blob is not None
    blob = Path(result.blob)
    assert blob.name == "tu_7.txt"
    assert blob.read_text(encoding="utf-8") == "x" * 1000
    assert "800 characters omitted" in result.text
    assert ".edgar/blobs/tu_7.txt" in result.text  # named relative to the working directory
    (finished,) = recorder.of(ToolFinished)
    assert finished.truncated is True


def test_error_record_names_only_what_the_harness_knows(tmp_project: Path) -> None:
    result = _run(tool_use("read", {"path": "missing.txt"}), _ctx(tmp_project))
    assert result.error is not None
    assert (result.error.tool, result.error.kind, result.error.exit_code) == (
        "read",
        "not_found",
        None,
    )


# execute_many(): consecutive `task` calls fan out, everything else stays in
# order, one at a time [TOOL-12].


class _Waiter:
    """A tool under any name that sleeps `seconds` before answering with its id."""

    def __init__(self, name: str, seconds: float = 0.1) -> None:
        self.seconds = seconds
        self.schema = ToolSchema(
            name=name,
            description="test tool",
            input_schema={"type": "object"},
            kind="builtin",
            origin="builtin",
            category="read",
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(self.seconds)
        return ToolResult(self.schema.name)


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ([], []),
        (["read"], [["read"]]),
        (["task"], [["task"]]),
        (["task", "task"], [["task", "task"]]),
        (["read", "task"], [["read"], ["task"]]),
        (["task", "read", "task"], [["task"], ["read"], ["task"]]),
        (["task", "task", "read", "task"], [["task", "task"], ["read"], ["task"]]),
    ],
)
def test_fan_out_group_splits_on_runs_of_task_calls(
    names: list[str], expected: list[list[str]]
) -> None:
    calls = [tool_use(n, {}, id=f"c{i}") for i, n in enumerate(names)]
    groups: list[list[str]] = []
    i = 0
    while i < len(calls):
        group = _fan_out_group(calls, i)
        groups.append([c.name for c in group])
        i += len(group)
    assert groups == expected


def _many(
    tmp_project: Path, calls: list[ToolUseBlock], registry: ToolRegistry, max_parallel: int = 4
) -> tuple[list[ToolResultBlock], float]:
    ctx = _ctx(tmp_project)
    gate = guard(tmp_project, "read-only")
    started = time.monotonic()
    results = asyncio.run(
        execute_many(
            calls,
            registry=registry,
            ctx=ctx,
            guard=gate,
            mode="read-only",
            tainted=False,
            max_parallel=max_parallel,
        )
    )
    return results, time.monotonic() - started


def test_execute_many_runs_consecutive_task_calls_concurrently(tmp_project: Path) -> None:
    registry = ToolRegistry([_Waiter("task", seconds=0.15)])
    calls = [tool_use("task", {}, id=f"t{i}") for i in range(3)]
    results, elapsed = _many(tmp_project, calls, registry)
    assert [r.text for r in results] == ["task", "task", "task"]
    assert elapsed < 0.15 * 2  # well under running them one at a time


def test_execute_many_bounds_concurrency_by_max_parallel(tmp_project: Path) -> None:
    registry = ToolRegistry([_Waiter("task", seconds=0.1)])
    calls = [tool_use("task", {}, id=f"t{i}") for i in range(4)]
    _, elapsed = _many(tmp_project, calls, registry, max_parallel=2)
    assert 0.1 * 2 <= elapsed < 0.1 * 4  # two batches of two, not four at once


def test_execute_many_keeps_non_task_calls_sequential(tmp_project: Path) -> None:
    registry = ToolRegistry([_Waiter("slow", seconds=0.1)])
    calls = [tool_use("slow", {}, id=f"s{i}") for i in range(2)]
    _, elapsed = _many(tmp_project, calls, registry)
    assert elapsed >= 0.1 * 2 - 0.02  # one at a time, not fanned out


def test_execute_many_preserves_call_order_across_a_fan_out(tmp_project: Path) -> None:
    registry = ToolRegistry([_Waiter("task", seconds=0.05), _Waiter("read", seconds=0)])
    calls = [
        tool_use("read", {}, id="r0"),
        tool_use("task", {}, id="t0"),
        tool_use("task", {}, id="t1"),
        tool_use("read", {}, id="r1"),
    ]
    results, _ = _many(tmp_project, calls, registry)
    assert [r.tool_use_id for r in results] == ["r0", "t0", "t1", "r1"]
