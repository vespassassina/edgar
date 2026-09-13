"""The tool pipeline: every failure comes back to the model, none raises [TOOL-2..4]."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from harness import Recorder, tool_use

from edgar.core.events import EventBus, ToolFinished
from edgar.core.message import ToolResultBlock, ToolUseBlock
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.execute import execute
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
    return asyncio.run(execute(call, registry=registry or core_registry(), ctx=ctx, mode="ask"))


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
