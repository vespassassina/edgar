"""Spawning a subagent: cycles, depth, mode, budget and failure [SUB-3..SUB-10]."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from harness import Recorder, guard, new_session, run_turn_sync, runtime, scripted, tool_use
from scripted import ScriptedResponse

from edgar.agents.definition import AgentBudget, AgentDefinition
from edgar.agents.spawn import HARD_DEPTH, SpawnLimits, _cap, narrow_mode, spawn, subagents_config
from edgar.config.schema import Config, ModelSection
from edgar.core.errors import ConfigError
from edgar.core.events import TurnStarted
from edgar.permissions.guard import Guard
from edgar.providers.base import Capabilities
from edgar.storage.transcript import sessions_dir
from edgar.tools.base import ToolContext, ToolResult, build_context
from edgar.tools.builtin.task import TaskTool
from edgar.tools.registry import ToolRegistry, core_registry


def _agent(
    name: str = "helper", model: str | None = None, budget: AgentBudget | None = None
) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        description="Helps.",
        path=Path("x.md"),
        prompt="Help.",
        model=model,
        budget=budget or AgentBudget(),
    )


def _run_spawn(
    agent: AgentDefinition,
    task: str,
    *,
    ctx: ToolContext,
    config: Config,
    guard: Guard,
    limits: SpawnLimits | None = None,
) -> ToolResult:
    coro = spawn(
        agent,
        task,
        ctx=ctx,
        limits=limits or SpawnLimits(),
        config=config,
        env=None,
        registry=core_registry(),
        guard=guard,
    )
    return asyncio.run(coro)


# narrow_mode [PERM-8]


@pytest.mark.parametrize(
    ("parent", "requested", "expected"),
    [
        ("ask", None, "ask"),  # no request: inherit the parent's
        ("auto", "read-only", "read-only"),  # narrower: honoured
        ("read-only", "auto", "read-only"),  # wider: refused, stays at the parent's
        ("ask", "ask", "ask"),  # equal: honoured
        ("yolo", "yolo", "yolo"),
    ],
)
def test_narrow_mode(parent: str, requested: str | None, expected: str) -> None:
    assert narrow_mode(parent, requested) == expected


# subagents_config [SUB-5, SUB-6]


def test_subagents_config_defaults_with_no_table() -> None:
    assert subagents_config({}) == SpawnLimits(max_parallel=4, max_depth=2)


def test_subagents_config_reads_the_table() -> None:
    limits = subagents_config({"subagents": {"max_parallel": 8, "max_depth": 3}})
    assert limits == SpawnLimits(max_parallel=8, max_depth=3)


def test_subagents_config_clamps_max_depth_to_the_hard_ceiling() -> None:
    limits = subagents_config({"subagents": {"max_depth": HARD_DEPTH + 10}})
    assert limits.max_depth == HARD_DEPTH


@pytest.mark.parametrize(
    "raw",
    [
        {"subagents": "not a table"},
        {"subagents": {"max_parallel": 0}},
        {"subagents": {"max_parallel": True}},
        {"subagents": {"max_depth": -1}},
    ],
)
def test_subagents_config_rejects_bad_values(raw: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        subagents_config(raw)


# _cap [SUB-7]


@pytest.mark.parametrize(
    ("own", "left", "expected"),
    [
        (None, None, None),
        (None, 5.0, 5.0),
        (3.0, None, 3.0),
        (3.0, 2.0, 2.0),
        (2.0, 5.0, 2.0),
    ],
)
def test_cap_never_exceeds_what_is_left_to_give(
    own: float | None, left: float | None, expected: float | None, tmp_project: Path
) -> None:
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    ctx = replace(ctx, budget_remaining=left)
    assert _cap(_agent(budget=AgentBudget(cost=own)), ctx) == expected


# spawn(): guards that need no provider [SUB-6, SUB-10]


def test_spawn_refuses_a_cycle(tmp_project: Path) -> None:
    session = new_session(tmp_project)
    session.agent_chain = ("helper",)
    ctx = build_context(session, runtime(scripted()))
    result = _run_spawn(_agent(), "do it", ctx=ctx, config=Config(), guard=guard(tmp_project))
    assert result.error == "validation"
    assert "helper" in result.text and "already running" in result.text


def test_spawn_refuses_past_the_depth_ceiling(tmp_project: Path) -> None:
    session = new_session(tmp_project)
    session.depth = 2
    ctx = build_context(session, runtime(scripted()))
    result = _run_spawn(
        _agent(),
        "do it",
        ctx=ctx,
        config=Config(),
        limits=SpawnLimits(max_depth=2),
        guard=guard(tmp_project),
    )
    assert result.error == "validation"
    assert "max_depth" in result.text


# spawn(): a subagent's own failure becomes a tool error, never a crash [SUB-8]


def test_spawn_turns_a_provider_failure_into_a_tool_error(tmp_project: Path) -> None:
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    config = Config(model=ModelSection(default="fake/test"))
    result = _run_spawn(
        _agent(model="fake/no-such-model"), "hi", ctx=ctx, config=config, guard=guard(tmp_project)
    )
    assert result.error == "internal"
    assert "helper" in result.text and "failed" in result.text


# spawn(): the agent's own `verify:` frontmatter authorises before its turn [VER-1, VER-4]


def test_spawn_denies_a_verify_command_its_guard_would_not_allow(tmp_project: Path) -> None:
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    config = Config(model=ModelSection(default="fake/test"))
    agent = AgentDefinition(
        name="helper", description="Helps.", path=Path("x.md"), prompt="Help.", verify="true"
    )
    result = _run_spawn(agent, "hi", ctx=ctx, config=config, guard=guard(tmp_project))
    assert result.error == "internal"
    assert "verify command" in result.text and "not allowed" in result.text


# spawn(): a model with no tool support is refused at selection [ROUTE-6]


def test_spawn_refuses_a_model_with_no_tool_support(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NoTools:
        capabilities = Capabilities(
            tools=False,
            parallel_tool_calls=False,
            streaming=True,
            reasoning=False,
            prompt_caching=False,
            max_context=1000,
            max_output=100,
        )

    monkeypatch.setattr("edgar.agents.spawn.resolve", lambda *a, **k: (NoTools(), "test"))
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    config = Config(model=ModelSection(default="fake/test"))
    result = _run_spawn(_agent(), "hi", ctx=ctx, config=config, guard=guard(tmp_project))
    assert result.error == "validation"
    assert "no tool support" in result.text


# spawn(): budget exhaustion is flagged, not hidden [SUB-7]


def test_spawn_flags_a_partial_result_when_the_budget_is_gone(tmp_project: Path) -> None:
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    ctx = replace(ctx, budget_remaining=0.0)
    config = Config(model=ModelSection(default="fake/test"))
    result = _run_spawn(_agent(), "hi", ctx=ctx, config=config, guard=guard(tmp_project))
    assert "[budget exhausted: partial result]" in result.text


# The `task` tool, end to end through the real loop: event scoping, permission
# labelling and transcript persistence for the subagent it spawns [SUB-4, SUB-9].


def test_task_tool_runs_a_scoped_subagent(tmp_project: Path, recorder: Recorder) -> None:
    g = guard(tmp_project, mode="auto")
    agents = {"helper": _agent()}
    tool = TaskTool(
        agents,
        core_registry(),
        g,
        Config(model=ModelSection(default="fake/test")),
        None,
        SpawnLimits(),
    )
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("task", {"agent": "helper", "task": "read a.txt"})]),
        ScriptedResponse(text="done"),
    )
    rt = replace(runtime(provider, recorder, tools=ToolRegistry([tool])), guard=g)
    session = new_session(tmp_project, mode="auto")
    result = run_turn_sync(session, "have the helper read a.txt", rt)

    assert result.text == "done"
    tool_result = session.transcript[2].tool_results[0]
    assert not tool_result.is_error
    assert "hello" in tool_result.text  # the subagent's own reply, echoed back up

    # The subagent's whole turn is stamped at depth 1 under its own agent id.
    starts = [e for e in recorder.of(TurnStarted) if e.depth == 1]
    assert len(starts) == 1 and starts[0].agent_id == "helper"

    # It ran as its own logged session, not folded into the parent's.
    assert len(list(sessions_dir(tmp_project).glob("*.jsonl"))) == 1


def test_task_tool_fans_out_two_consecutive_calls(tmp_project: Path, recorder: Recorder) -> None:
    g = guard(tmp_project, mode="auto")
    agents = {"helper": _agent("helper"), "reader": _agent("reader")}
    tool = TaskTool(
        agents,
        core_registry(),
        g,
        Config(model=ModelSection(default="fake/test")),
        None,
        SpawnLimits(),
    )
    provider = scripted(
        ScriptedResponse(
            tool_calls=[
                tool_use("task", {"agent": "helper", "task": "read a.txt"}, id="tu1"),
                tool_use("task", {"agent": "reader", "task": "read a.txt"}, id="tu2"),
            ]
        ),
        ScriptedResponse(text="done"),
    )
    rt = replace(runtime(provider, recorder, tools=ToolRegistry([tool])), guard=g)
    session = new_session(tmp_project, mode="auto")
    result = run_turn_sync(session, "have both read a.txt", rt)

    assert result.text == "done"
    results = session.transcript[2].tool_results
    assert [r.tool_use_id for r in results] == ["tu1", "tu2"]  # call order, not finish order
    assert all(not r.is_error and "hello" in r.text for r in results)

    # Both subagents ran, each stamped with its own agent id at depth 1.
    starts = {e.agent_id for e in recorder.of(TurnStarted) if e.depth == 1}
    assert starts == {"helper", "reader"}

    # Each got its own logged session.
    assert len(list(sessions_dir(tmp_project).glob("*.jsonl"))) == 2


# TaskTool itself: what the model sees, and what a bad call looks like [TOOL-12]


def _task_tool(tmp_project: Path) -> TaskTool:
    return TaskTool(
        {"reviewer": _agent("reviewer"), "planner": _agent("planner")},
        core_registry(),
        guard(tmp_project),
        Config(model=ModelSection(default="fake/test")),
        None,
        SpawnLimits(),
    )


def test_task_tool_schema_lists_every_agent(tmp_project: Path) -> None:
    schema = _task_tool(tmp_project).schema
    assert schema.category == "agent"
    assert schema.input_schema["properties"]["agent"]["enum"] == ["planner", "reviewer"]
    assert "reviewer" in schema.description and "planner" in schema.description


def test_task_tool_names_the_agent_and_the_task_in_its_subject(tmp_project: Path) -> None:
    tool = _task_tool(tmp_project)
    subject = tool.subject({"agent": "reviewer", "task": "check the diff"}, tmp_project)
    assert subject.text == "agent reviewer: check the diff"


def test_task_tool_reports_an_unknown_agent(tmp_project: Path) -> None:
    tool = _task_tool(tmp_project)
    ctx = build_context(new_session(tmp_project), runtime(scripted()))
    result = asyncio.run(tool.run({"agent": "no-such-agent", "task": "do it"}, ctx))
    assert result.error == "not_found"
    assert "reviewer" in result.text and "planner" in result.text
