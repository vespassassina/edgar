"""Every tool call, from every source, takes the same path [TOOL-2, TOOL-3, TOOL-4].

    validate → (pre_tool hooks, v1) → permission → run with timeout → spill

Each failure becomes a ToolResultBlock(is_error=True) with an ErrorRecord the
harness computed, and goes back to the model, which often recovers by trying
something else. Nothing here raises into the loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from edgar.core.events import ToolFinished, ToolProposed, ToolStarted
from edgar.core.message import ErrorKind, ErrorRecord, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Deny
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.registry import ToolRegistry
from edgar.tools.spill import spill


async def execute(
    call: ToolUseBlock,
    *,
    registry: ToolRegistry,
    ctx: ToolContext,
    guard: Guard,
    mode: str,
    tainted: bool = False,
) -> ToolResultBlock:
    bus = ctx.bus
    bus.emit(ToolProposed(id=call.id, tool=call.name, args_preview=preview(call.args)))
    tool = registry.get(call.name)
    if tool is None:
        known = ", ".join(registry.names())
        return _failed(call, "not_found", f"unknown tool {call.name!r}; available: {known}")

    if call.malformed is not None:
        return _failed(
            call,
            "validation",
            f"arguments for {call.name} are not a JSON object: {call.malformed[:200]!r}. "
            "Send the arguments as one JSON object matching the tool's schema.",
        )
    problem = _validate(tool.schema, call.args)
    if problem is not None:
        return _failed(call, "validation", problem)

    described = getattr(tool, "subject", None)  # command and HTTP tools say what they touch
    decision = await guard.check(
        tool.schema,
        call.args,
        cwd=ctx.cwd,
        mode=mode,
        tainted=tainted,
        call_id=call.id,
        bus=bus,
        subject=described(call.args, ctx.cwd) if described else None,
    )
    if isinstance(decision, Deny):
        return _failed(call, "permission_denied", f"denied: {decision.reason}")

    bus.emit(ToolStarted(id=call.id, tool=call.name))
    timeout = getattr(tool, "timeout_s", None) or ctx.timeout_s
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(tool.run(call.args, ctx), timeout)
    except TimeoutError:
        result = ToolResult(f"timed out after {timeout:g} s", error="timeout")
    except Exception as exc:  # a crashing tool must not take the turn down with it
        result = ToolResult(f"{call.name} failed: {type(exc).__name__}: {exc}", error="internal")

    out = spill(
        result.text,
        max_tokens=ctx.max_output_tokens,
        blob_dir=ctx.blob_dir,
        name=call.id,
        root=ctx.cwd,
    )
    block = ToolResultBlock(
        call.id,
        (TextBlock(out.text),),
        is_error=result.error is not None,
        truncated=out.truncated,
        untrusted=tool.schema.untrusted_output,
        error=ErrorRecord(call.name, result.error, result.exit_code, result.program)
        if result.error
        else None,
        blob=out.blob.as_posix() if out.blob else None,
    )
    bus.emit(
        ToolFinished(
            id=call.id,
            ok=not block.is_error,
            duration_ms=round((time.monotonic() - started) * 1000),
            truncated=block.truncated,
            blob=block.blob,
        )
    )
    return block


def _validate(schema: ToolSchema, args: dict[str, Any]) -> str | None:
    # jsonschema costs ~30 ms to import; only runs that call a tool pay for it (NFR-1).
    from jsonschema import Draft202012Validator

    errors = sorted(Draft202012Validator(schema.input_schema).iter_errors(args), key=str)
    if not errors:
        return None
    details = "; ".join(
        f"{'.'.join(map(str, e.absolute_path)) or 'arguments'}: {e.message}" for e in errors
    )
    return f"invalid arguments for {schema.name}: {details}"


def _failed(call: ToolUseBlock, kind: ErrorKind, text: str) -> ToolResultBlock:
    return ToolResultBlock(
        call.id, (TextBlock(text),), is_error=True, error=ErrorRecord(call.name, kind)
    )


def preview(args: dict[str, Any], limit: int = 120) -> str:
    text = json.dumps(args, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[: limit - 1] + "…"
