"""Escalation upward on repeated failure, capped, always announced
[ROUTE-5, ROUTE-10, ADR-0013]."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from scripted import ScriptedProvider

from edgar.core.errors import ConfigError
from edgar.core.events import Escalation, EventBus
from edgar.core.loop import Runtime, _Turn
from edgar.core.message import ErrorKind, ErrorRecord, ToolResultBlock
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy
from edgar.providers.base import Usage
from edgar.providers.escalation import (
    EscalationConfig,
    EscalationState,
    Triggers,
    _due,
    chain_from_config,
)
from edgar.tools.base import ToolContext
from edgar.tools.registry import core_registry

ROOT = Path("/tmp/edgar-test-escalation")


class _OtherFamily(ScriptedProvider):
    family = "other"


def _guard() -> Guard:
    return Guard(Policy(mode="read-only", cwd=ROOT, home=ROOT.parent))


def _ctx() -> ToolContext:
    return ToolContext(cwd=ROOT, bus=EventBus(), blob_dir=ROOT / "blobs", max_output_tokens=8000)


def _rt(provider: ScriptedProvider, escalation: EscalationState | None = None) -> Runtime:
    bus = EventBus()
    return Runtime(
        provider=provider,
        model="test",
        tools=core_registry(),
        system_prompt="",
        bus=bus,
        max_output_tokens=8000,
        name="a/test",
        guard=_guard(),
        escalation=escalation,
    )


def _turn(*, results: list[ToolResultBlock] | None = None, repairs: int = 0) -> _Turn:
    return _Turn(
        id="t",
        ctx=_ctx(),
        guard=_guard(),
        usage=Usage(repairs=repairs),
        results=list(results or []),
    )


def _failed(kind: ErrorKind = "not_found") -> ToolResultBlock:
    return ToolResultBlock(
        "tu_1", content=(), is_error=True, error=ErrorRecord(tool="x", kind=kind)
    )


def _ok() -> ToolResultBlock:
    return ToolResultBlock("tu_1", content=())


def test_current_is_the_session_model_until_escalated() -> None:
    provider = ScriptedProvider()
    state = EscalationState(chain=(("b/test", provider, "b"),), max_escalations=1, on=Triggers())
    rt = _rt(provider, state)
    assert state.current(rt) == (provider, "test", "a/test")


def test_current_is_the_chain_model_once_escalated() -> None:
    provider = ScriptedProvider()
    stronger = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", stronger, "b-model"),), max_escalations=1, on=Triggers(), index=1
    )
    rt = _rt(provider, state)
    assert state.current(rt) == (stronger, "b-model", "b/test")


def test_after_round_does_nothing_below_threshold() -> None:
    provider = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", provider, "b"),), max_escalations=1, on=Triggers(consecutive_failures=2)
    )
    rt = _rt(provider, state)
    state.after_round(rt, _turn(results=[_failed()]))
    assert state.index == 0


def test_after_round_escalates_on_consecutive_failures() -> None:
    provider = ScriptedProvider()
    stronger = ScriptedProvider()
    bus = EventBus()
    events: list[Escalation] = []
    bus.subscribe(lambda e: events.append(e) if isinstance(e, Escalation) else None)
    state = EscalationState(
        chain=(("b/test", stronger, "b-model"),),
        max_escalations=1,
        on=Triggers(consecutive_failures=2),
    )
    rt = replace(_rt(provider, state), bus=bus)
    state.after_round(rt, _turn(results=[_failed()]))
    state.after_round(rt, _turn(results=[_failed()]))
    assert state.index == 1
    assert len(events) == 1
    assert events[0].from_model == "a/test"
    assert events[0].to_model == "b/test"


def test_after_round_resets_on_a_clean_round() -> None:
    provider = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", provider, "b"),), max_escalations=1, on=Triggers(consecutive_failures=2)
    )
    rt = _rt(provider, state)
    state.after_round(rt, _turn(results=[_failed()]))
    state.after_round(rt, _turn(results=[_ok()]))
    state.after_round(rt, _turn(results=[_failed()]))
    assert state.index == 0  # never reached two IN A ROW


def test_after_round_escalates_on_tool_call_errors() -> None:
    provider = ScriptedProvider()
    stronger = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", stronger, "b-model"),), max_escalations=1, on=Triggers(tool_call_errors=2)
    )
    rt = _rt(provider, state)
    state.after_round(rt, _turn(results=[_failed("timeout"), _failed("timeout")]))
    assert state.index == 1


def test_after_round_escalates_on_schema_violations() -> None:
    provider = ScriptedProvider()
    stronger = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", stronger, "b-model"),),
        max_escalations=1,
        on=Triggers(schema_violations=2),
    )
    rt = _rt(provider, state)
    state.after_round(rt, _turn(repairs=2))
    assert state.index == 1


def test_after_round_never_exceeds_max_escalations() -> None:
    provider = ScriptedProvider()
    b = ScriptedProvider()
    c = ScriptedProvider()
    state = EscalationState(
        chain=(("b/test", b, "b-model"), ("c/test", c, "c-model")),
        max_escalations=1,
        on=Triggers(consecutive_failures=1),
    )
    rt = _rt(provider, state)
    state.after_round(rt, _turn(results=[_failed()]))
    state.after_round(rt, _turn(results=[_failed()]))
    assert state.index == 1  # capped below the chain's own length


def test_crossing_families_drops_reasoning() -> None:  # [PRV-13]
    provider = ScriptedProvider()
    other = _OtherFamily()
    state = EscalationState(
        chain=(("b/test", other, "b-model"),),
        max_escalations=1,
        on=Triggers(consecutive_failures=1),
    )
    rt = _rt(provider, state)
    turn = _turn(results=[_failed()])
    state.after_round(rt, turn)
    assert turn.reasoning is False


def test_due_ignores_a_disabled_trigger() -> None:
    state = EscalationState(chain=(), max_escalations=0, on=Triggers())
    assert _due(state, _turn(results=[_failed()], repairs=99)) is False


def test_chain_from_config_parses_the_table() -> None:
    later = {"model.escalation": {"chain": ["a/one", "b/two"], "on": {"tool_call_errors": 2}}}
    plan = chain_from_config(later)
    assert plan == EscalationConfig(("a/one", "b/two"), 2, Triggers(tool_call_errors=2))


def test_chain_from_config_defaults_max_escalations_to_the_chain_length() -> None:
    plan = chain_from_config({"model.escalation": {"chain": ["a/one", "b/two"]}})
    assert plan is not None
    assert plan.max_escalations == 2


def test_no_escalation_key_is_none() -> None:
    assert chain_from_config({}) is None


def test_enabled_false_is_none() -> None:
    later = {"model.escalation": {"enabled": False, "chain": ["a/one"]}}
    assert chain_from_config(later) is None


@pytest.mark.parametrize(
    "later",
    [
        {"model.escalation": {"chain": "not a list"}},
        {"model.escalation": {"chain": []}},
        {"model.escalation": {"chain": [""]}},
    ],
)
def test_a_malformed_chain_is_a_config_error(later: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        chain_from_config(later)


def test_an_unknown_trigger_is_a_config_error() -> None:
    later = {"model.escalation": {"chain": ["a/one"], "on": {"not_a_trigger": 1}}}
    with pytest.raises(ConfigError):
        chain_from_config(later)


def test_on_not_a_table_is_a_config_error() -> None:
    later = {"model.escalation": {"chain": ["a/one"], "on": "not a table"}}
    with pytest.raises(ConfigError):
        chain_from_config(later)
