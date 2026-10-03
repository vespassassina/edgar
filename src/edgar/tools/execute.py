"""Every tool call, from every source, takes the same path [TOOL-2, TOOL-3, TOOL-4].

    validate → pre_tool hooks → ticket → permission → run with timeout → spill

Each failure becomes a ToolResultBlock(is_error=True) with an ErrorRecord the
harness computed, and goes back to the model, which often recovers by trying
something else. Nothing here raises into the loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from edgar.core.events import ScopeRefused, ToolFinished, ToolProposed, ToolStarted
from edgar.core.message import ErrorKind, ErrorRecord, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.extensions.hooks import veto as hooks_veto
from edgar.permissions.guard import Guard
from edgar.permissions.matcher import subject as resolve
from edgar.permissions.policy import Deny, category, network_allowed
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.registry import ToolRegistry
from edgar.tools.spill import spill

READ_PARALLEL = 8  # reads in flight at once; a read is cheap, a task is a whole agent


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

    if ctx.hooks:
        reason = await hooks_veto(
            ctx.hooks, {"tool": call.name, "args": call.args}, cwd=ctx.cwd, bus=bus
        )
        if reason is not None:
            return _failed(call, "permission_denied", f"denied by hook: {reason}")

    described = getattr(tool, "subject", None)  # command and HTTP tools say what they touch
    subj = described(call.args, ctx.cwd) if described else resolve(call.args, ctx.cwd)

    if ctx.broker is not None:
        refusal = ctx.broker.check(
            tool=call.name, read_only=tool.schema.read_only, subject=subj, cwd=ctx.cwd
        )
        if refusal is not None:
            caveat, reason = refusal
            bus.emit(ScopeRefused(id=call.id, tool=call.name, caveat=caveat, reason=reason))
            return _failed(call, "out_of_scope", f"refused by scope: {reason}")

    decision = await guard.check(
        tool.schema,
        call.args,
        cwd=ctx.cwd,
        mode=mode,
        tainted=tainted,
        call_id=call.id,
        bus=bus,
        subject=subj,
        agent_id=ctx.chain[-1] if ctx.chain else "main",
    )
    if isinstance(decision, Deny):
        return _failed(call, "permission_denied", f"denied: {decision.reason}")

    # The sandbox is told what the engine just decided, read fresh: taint is sticky
    # but can be set by an earlier call in this same turn [PERM-15, PERM-11].
    ctx = replace(ctx, network=network_allowed(mode, tainted))
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
        images=(result.image,) if result.image else (),
    )
    bus.emit(
        ToolFinished(
            id=call.id,
            tool=call.name,
            ok=not block.is_error,
            duration_ms=round((time.monotonic() - started) * 1000),
            truncated=block.truncated,
            blob=block.blob,
            image=result.image.ref if result.image else None,
            error=block.error,  # the record, never the message [MEM-22]
        )
    )
    return block


async def execute_many(
    calls: Sequence[ToolUseBlock],
    *,
    registry: ToolRegistry,
    ctx: ToolContext,
    guard: Guard,
    mode: str,
    tainted: bool,
    max_parallel: int,
) -> list[ToolResultBlock]:
    # One call at a time, except a run of consecutive `task` calls (bounded by
    # max_parallel) or a run of consecutive reads (bounded by READ_PARALLEL),
    # which go together; results still come back in call order either way, so
    # a caller's own bookkeeping never races [TOOL-12, ADR-0074].
    tasks = asyncio.Semaphore(max(max_parallel, 1))
    reads = asyncio.Semaphore(READ_PARALLEL)

    async def bounded(call: ToolUseBlock) -> ToolResultBlock:
        async with tasks if call.name == "task" else reads:
            return await execute(
                call, registry=registry, ctx=ctx, guard=guard, mode=mode, tainted=tainted
            )

    results: list[ToolResultBlock] = []
    i = 0
    while i < len(calls):
        group = _fan_out_group(calls, i, registry)
        results.extend(await asyncio.gather(*(bounded(c) for c in group)))
        i += len(group)
    return results


def _kind(call: ToolUseBlock, registry: ToolRegistry) -> str | None:
    # "task", "read", or None for a call that always runs on its own. `todo` says
    # "read" but writes the session's list, so its order matters.
    if call.name == "task":
        return "task"
    tool = registry.get(call.name)
    if tool is None or call.name == "todo" or category(tool.schema) != "read":
        return None
    return "read"


def _fan_out_group(
    calls: Sequence[ToolUseBlock], i: int, registry: ToolRegistry
) -> Sequence[ToolUseBlock]:
    """`calls[i]` alone, unless it starts a run of calls of one kind that may overlap."""
    kind = _kind(calls[i], registry)
    j = i + 1
    while kind and j < len(calls) and _kind(calls[j], registry) == kind:
        j += 1
    return calls[i:j]


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
