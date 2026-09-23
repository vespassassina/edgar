# schedule_self: the model's own way to schedule a future run of this project
# [SCH-11]. A run can never grant itself more than it already has:
#
# 1. mode never widens past the calling session's own mode [PERM-8], the same
#    rule agents/spawn.py's narrow_mode() gives a subagent.
# 2. scope and allowlist attenuate the caller's live ticket, when one exists,
#    through the same narrowed() a subagent's `scope` argument uses [CAP-5];
#    with no ticket at all, there is nothing further to attenuate.
# 3. a pending-entry cap and a rolling per-day rate limit, both read from the
#    store before a row is written.
# 4. a depth ceiling on self-schedules chaining into more self-schedules, read
#    from an env marker only run.py's runner_for() sets, never from the model,
#    so the guard cannot be talked past by a cooperative-sounding argument.

from __future__ import annotations

from typing import Any

from edgar.agents.spawn import narrow_mode
from edgar.schedule.due import parse_when
from edgar.schedule.parser import CATCH_UP_POLICIES
from edgar.schedule.store import MAX_DEPTH, MAX_PENDING, MAX_PER_DAY, SelfSchedules
from edgar.tools.base import ToolContext, ToolResult, builtin_schema

DAY = 86400.0


class ScheduleSelfTool:
    def __init__(self, store: SelfSchedules, depth: int) -> None:
        self.store, self.depth = store, depth
        self.schema = builtin_schema(
            "schedule_self",
            "Schedule a future run of this project: a follow-up check, a reminder, "
            "a recurring job. Never grants more authority than you already have.",
            {
                "name": {"type": "string"},
                "when": {"type": "string", "description": "@daily, @hourly, cron, or 'every 15m'"},
                "prompt": {"type": "string"},
                "mode": {"type": "string", "enum": ["read-only", "ask", "auto", "yolo"]},
                "allowlist": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "array", "items": {"type": "string"}},
                "catch_up": {"type": "string", "enum": list(CATCH_UP_POLICIES)},
            },
            ["name", "when", "prompt"],
            category="agent",
            dangerous=True,
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        refusal = self._refusal()
        if refusal is not None:
            return ToolResult(refusal, error="permission_denied")
        try:
            parse_when(args["when"])
        except Exception as exc:
            return ToolResult(f"bad `when`: {exc}", error="validation")
        mode = narrow_mode(ctx.mode, args.get("mode"))
        scope, allowlist = self._attenuated(ctx, args)
        entry = self.store.add(
            name=args["name"],
            when=args["when"],
            prompt=args["prompt"],
            mode=mode,
            allowlist=allowlist,
            scope=scope,
            catch_up=args.get("catch_up", "once"),
            depth=self.depth + 1,
        )
        return ToolResult(f"scheduled {entry.name!r} ({args['when']}), mode={mode}")

    def _refusal(self) -> str | None:
        if self.depth + 1 > MAX_DEPTH:
            return f"refused: self-schedules may not nest past depth {MAX_DEPTH} [SCH-11]"
        if self.store.pending_count() >= MAX_PENDING:
            return f"refused: {MAX_PENDING} self-schedules are already pending"
        if self.store.created_since(DAY) >= MAX_PER_DAY:
            return f"refused: at most {MAX_PER_DAY} new self-schedules a day"
        return None

    def _attenuated(
        self, ctx: ToolContext, args: dict[str, Any]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        allowlist = tuple(args.get("allowlist") or ())
        scope = tuple(args.get("scope") or ())
        if ctx.broker is None:
            return scope, allowlist
        from edgar.broker.guard import TicketGuard  # sibling v4 package [ADR-0015]

        narrowed = ctx.broker.narrowed(
            subject=f"schedule:{args['name']}", tools=allowlist, scope=scope
        )
        if not isinstance(narrowed, TicketGuard):
            return scope, allowlist
        return tuple(f"{c.kind}={c.value}" for c in narrowed.ticket.caveats), allowlist
