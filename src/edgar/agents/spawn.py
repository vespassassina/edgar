"""Spawning a subagent: the `task` tool re-enters the loop with a narrower
policy and a fresh transcript [SUB-3..SUB-10, ADR-0006].
"""

# One `task` call, as pseudocode:
#
#   refuse if this agent is already running in the call chain      [SUB-10]
#   refuse past the depth ceiling                                  [SUB-6]
#   narrow the mode: never wider than the caller's                 [PERM-8]
#   pick its model: its own, or routing for role "subagent"        [ROUTE-1]
#   filter the registry to the agent's own `tools:` list
#   give it what is left of the caller's budget                    [SUB-7]
#   with `isolation: worktree`, cut it a git worktree and put its
#   session's cwd there, so every path rule moves with it          [SUB-11]
#   run a fresh, logged session with the agent's own prompt as its
#   system prompt and the task text as its only turn               [SUB-3, SUB-4]
#   turn a raised exception into a tool error, never a crash        [SUB-8]
#   close the worktree either way, and say what became of it       [SUB-11]

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from edgar.agents import worktree
from edgar.agents.definition import AgentDefinition
from edgar.config.schema import BudgetSection, Config, Mode
from edgar.core.errors import ConfigError, EdgarError
from edgar.core.loop import Runtime, run_turn
from edgar.core.session import Session
from edgar.core.verify import Check
from edgar.core.verify import authorise as verify_authorise
from edgar.permissions.guard import Guard
from edgar.providers.fallback import chain_from_config
from edgar.providers.registry import resolve
from edgar.providers.routing import (
    RoutingContext,
    check_capabilities,
    routes_from_config,
    select_model,
)
from edgar.storage.transcript import start
from edgar.tools.base import ToolContext, ToolResult
from edgar.tools.registry import ToolRegistry

HARD_DEPTH = 5  # never raised by config [SUB-6]
_MODE_RANK = {"read-only": 0, "ask": 1, "auto": 2, "yolo": 3}


@dataclass(frozen=True, slots=True)
class SpawnLimits:
    max_parallel: int = 4  # [SUB-5]
    max_depth: int = 2  # [SUB-6]


def subagents_config(later: dict[str, Any]) -> SpawnLimits:
    """`[subagents]` arrives in `Config.later["subagents"]`; this is where v1
    finally reads it."""
    raw = later.get("subagents", {})
    if not isinstance(raw, dict):
        raise ConfigError('[subagents] must be a table, written "[subagents]"')
    parallel, depth = raw.get("max_parallel", 4), raw.get("max_depth", 2)
    if not isinstance(parallel, int) or isinstance(parallel, bool) or parallel < 1:
        raise ConfigError("[subagents] max_parallel must be a positive integer")
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
        raise ConfigError("[subagents] max_depth must be a positive integer")
    return SpawnLimits(max_parallel=parallel, max_depth=min(depth, HARD_DEPTH))


def narrow_mode(parent: str, requested: str | None) -> str:
    """A subagent's own `mode:` never widens the parent's [PERM-8]."""
    if requested is None:
        return parent
    return requested if _MODE_RANK[requested] <= _MODE_RANK[parent] else parent


async def spawn(
    agent: AgentDefinition,
    task: str,
    *,
    ctx: ToolContext,
    limits: SpawnLimits,
    config: Config,
    env: Mapping[str, str] | None,
    registry: ToolRegistry,
    guard: Guard,
) -> ToolResult:
    if agent.name in ctx.chain:
        return ToolResult(
            f"{agent.name} is already running in this call chain "
            f"({' -> '.join((*ctx.chain, agent.name))})",
            error="validation",
        )
    depth = ctx.depth + 1
    if depth > limits.max_depth:
        return ToolResult(
            f"subagent depth would reach {depth}, past this project's max_depth "
            f"({limits.max_depth})",
            error="validation",
        )
    mode = narrow_mode(ctx.mode, agent.mode)
    routing = RoutingContext(
        role="subagent",
        agent=agent.name,
        agent_model=agent.model,
        mode=cast(Mode, mode),  # narrow_mode only ever returns one of Mode's own values
        tools_required=bool(agent.tools),
    )
    selection = select_model(routing, config.model, routes_from_config(config.later))
    provider, model = resolve(selection.model, config, env=env)
    fallback = tuple(
        (name, *resolve(name, config, env=env)) for name in chain_from_config(config.later)
    )
    tools = registry if not agent.tools else _subset(registry, agent.tools)
    try:  # a model with no tool support caught here, not mid-turn [ROUTE-6]
        check_capabilities(
            selection, tools_required=bool(tools.names()), has_tools=provider.capabilities.tools
        )
    except EdgarError as exc:
        return ToolResult(str(exc), error="validation")
    session = Session(
        cwd=ctx.cwd,
        model=selection.model,
        mode=mode,
        depth=depth,
        agent_chain=(*ctx.chain, agent.name),
    )
    tree = None
    if agent.isolation == worktree.ISOLATION:
        # The session id names the tree, so two runs of the same agent never collide.
        tree, refusal = await worktree.create(ctx.cwd, agent.name, session.id)
        if tree is None:  # no worktree, no run: never a quiet fallback [SUB-11]
            return ToolResult(refusal, error="validation")
        session.cwd = tree.path  # the whole rebase: ToolContext.cwd follows Session.cwd
    session = start(session)
    check = None
    if agent.verify:  # the agent's own frontmatter, ahead of a loaded skill's [VER-1]
        # The same walls the parent's `shell` runs in: a subagent never widens them.
        walls = getattr(registry.get("shell"), "sandbox", None)
        check = Check(agent.verify, config.verify.max_attempts, config.shell.program, walls)
    rt = Runtime(
        provider=provider,
        model=model,
        tools=tools,
        system_prompt=agent.prompt,
        bus=ctx.bus.scoped(agent_id=agent.name, depth=depth),
        max_output_tokens=ctx.max_output_tokens,
        name=selection.model,
        guard=guard,
        verify=check,
        budget=BudgetSection(session_cost_cap=_cap(agent, ctx)),
        fallback=fallback,
    )
    try:
        if check is not None:  # authorised before the turn starts, like the main session [VER-4]
            await verify_authorise(check, guard, session, rt.bus)
        result = await run_turn(session, task, rt)
    except Exception as exc:  # a subagent's own failure surfaces as a tool error [SUB-8]
        return ToolResult(
            f"agent {agent.name!r} failed: {type(exc).__name__}: {exc}{await _closed(tree)}",
            error="internal",
        )
    flag = " [budget exhausted: partial result]" if result.reason == "budget_exceeded" else ""
    return ToolResult(f"{result.text}{flag}{await _closed(tree)}")


async def _closed(tree: worktree.Worktree | None) -> str:
    # Always in the summary the model and the human both read, both outcomes [SUB-11].
    return "" if tree is None else f"\n\n{await worktree.finish(tree)}"


def _cap(agent: AgentDefinition, ctx: ToolContext) -> float | None:
    # A per-agent budget never exceeds what the caller has left to give [SUB-7].
    own, left = agent.budget.cost, ctx.budget_remaining
    if own is None:
        return left
    return min(own, left) if left is not None else own


def _subset(registry: ToolRegistry, names: tuple[str, ...]) -> ToolRegistry:
    return ToolRegistry([t for n in names if (t := registry.get(n)) is not None])
