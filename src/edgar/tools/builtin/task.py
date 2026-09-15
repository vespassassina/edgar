"""The `task` tool: a subagent is this same loop, re-entered with a narrower
policy and a fresh transcript, never a second engine [ADR-0006]."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from edgar.agents.definition import AgentDefinition
from edgar.agents.spawn import SpawnLimits, spawn
from edgar.config.schema import Config
from edgar.permissions.guard import Guard
from edgar.permissions.matcher import Subject
from edgar.tools.base import ToolContext, ToolResult, builtin_schema
from edgar.tools.registry import ToolRegistry


class TaskTool:
    def __init__(
        self,
        agents: dict[str, AgentDefinition],
        registry: ToolRegistry,
        guard: Guard,
        config: Config,
        env: Mapping[str, str] | None,
        limits: SpawnLimits,
    ) -> None:
        self.agents, self.registry, self.guard = agents, registry, guard
        self.config, self.env, self.limits = config, env, limits
        listed = "\n".join(f"- {a.name}: {a.description}" for a in agents.values())
        self.schema = builtin_schema(
            "task",
            f"Run a subagent in a fresh context, with its own model, tools and policy. "
            f"Use one when its description fits the work. Agents available:\n{listed}",
            {
                "agent": {"type": "string", "enum": sorted(agents)},
                "task": {"type": "string", "description": "what the subagent should do"},
            },
            ["agent", "task"],
            category="agent",
        )

    def subject(self, args: dict[str, Any], cwd: Path) -> Subject:
        return Subject(f"agent {args.get('agent')}: {str(args.get('task', ''))[:80]}")

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        agent = self.agents.get(args["agent"])
        if agent is None:
            listed = ", ".join(sorted(self.agents))
            return ToolResult(f"no agent {args['agent']!r}; there are: {listed}", error="not_found")
        return await spawn(
            agent,
            args["task"],
            ctx=ctx,
            limits=self.limits,
            config=self.config,
            env=self.env,
            registry=self.registry,
            guard=self.guard,
        )
