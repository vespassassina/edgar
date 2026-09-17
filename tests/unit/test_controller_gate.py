"""The gate: what it costs when nothing is wrong, and what it cannot do when
something is [CTRL-1, CTRL-2, CTRL-3, CTRL-9, CTRL-11].

The model here is the scripted fake, so every "answer from the controller" below is
a fabricated proposal, same as the rest of the controller's tests. What is under
test is the machinery around it: whether a call happens at all, what that call is
allowed to carry, and what happens when the answer is wrong or the call explodes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from scripted import ScriptedProvider, ScriptedResponse

import edgar.controller.gate as gate_module
from edgar.config.schema import Config, ControllerSection, ModelSection
from edgar.controller import attach, overrides
from edgar.controller.gate import Gate
from edgar.controller.store import Controls
from edgar.core.events import (
    ControllerActed,
    Event,
    EventBus,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy
from edgar.providers.base import Usage

FINE = Usage(input_tokens=10, output_tokens=10)
HUGE = Usage(input_tokens=9_000, output_tokens=10)  # 90% of the 10,000 window below

# The scripted provider the patched resolve() hands back, set by _gate().
LAST: list[ScriptedProvider] = []


@pytest.fixture(autouse=True)
def _no_real_host(monkeypatch: pytest.MonkeyPatch) -> None:
    # resolve() would reach the registry and a configured host. Every test here
    # scripts its own provider instead, and this is what hands it over.
    def fake_resolve(model: str, config: Any = None, **kw: Any) -> tuple[Any, str]:
        return LAST[-1], "test"

    monkeypatch.setattr(gate_module, "resolve", fake_resolve)
    LAST.clear()


def _config(**controller: Any) -> Config:
    return replace(
        Config(),
        model=ModelSection(default="fake/test"),
        controller=ControllerSection(enabled=True, **controller),
    )


def _gate(tmp_path: Path, *answers: ScriptedResponse, config: Config | None = None) -> Gate:
    LAST.append(ScriptedProvider(list(answers)))
    return Gate(
        config=config or _config(),
        root=tmp_path,
        home=tmp_path,
        guard=Guard(Policy(mode="auto", cwd=tmp_path, home=tmp_path)),
        store=Controls(tmp_path / ".edgar" / "controller.db"),
        bus=EventBus(),
        window=10_000,
    )


def says(answer: str) -> ScriptedResponse:
    return ScriptedResponse(text=answer)


def _finished(usage: Usage, reason: str = "stop") -> TurnFinished:
    return TurnFinished(turn_id="t1", usage=usage, cost=0.0, reason=reason)


def _started() -> TurnStarted:
    return TurnStarted(turn_id="t1", model="fake/test")


def _failure() -> ToolFinished:
    return ToolFinished(id="a", tool="shell", ok=False, duration_ms=1, truncated=False, blob=None)


def _turn(gate: Gate, events: Iterable[Event]) -> None:
    # The bus is synchronous and the gate's own call is not, so the events go in
    # inside a loop, which is then given a few turns to finish the background task.
    async def go() -> None:
        for event in events:
            gate(event)
        for _ in range(8):
            await asyncio.sleep(0)

    asyncio.run(go())


def _acted(gate: Gate) -> list[ControllerActed]:
    seen: list[ControllerActed] = []
    gate.bus.subscribe(lambda e: seen.append(e) if isinstance(e, ControllerActed) else None)
    return seen


def test_an_ordinary_turn_costs_nothing_at_all(tmp_path: Path) -> None:
    # The reason the triggers are deterministic: no model decides whether to call a
    # model, and a turn that trips nothing makes no request [CTRL-2].
    gate = _gate(tmp_path, says('{"action": "noop"}'))
    _turn(gate, [_started(), _finished(FINE)])
    assert LAST[-1].call_count == 0
    assert gate.store.mutations() == []


def test_a_tripped_check_is_one_call_and_it_carries_no_tools(tmp_path: Path) -> None:
    # CTRL-3 as built: the hard limit on the controller's tool set is zero.
    gate = _gate(tmp_path, says('{"action": "noop", "reason": "long but fine"}'))
    _turn(gate, [_started(), _finished(HUGE)])
    assert LAST[-1].call_count == 1
    assert LAST[-1].tools_seen == [[]]
    assert gate.store.mutations()[0].action == "noop"


def test_the_controller_is_told_counts_and_names_and_never_tool_output(tmp_path: Path) -> None:
    gate = _gate(tmp_path, says('{"action": "noop"}'))
    _turn(gate, [_started(), _failure(), _finished(HUGE)])
    sent = LAST[-1].requests[0][0].text
    assert "tools called: shell" in sent
    assert "calls that failed: 1" in sent
    assert "context 90% of the window" in sent


def test_always_mode_looks_at_every_turn(tmp_path: Path) -> None:
    gate = _gate(tmp_path, says('{"action": "noop"}'), config=_config(mode="always"))
    _turn(gate, [_started(), _finished(FINE)])
    assert LAST[-1].call_count == 1


def test_a_streak_needs_failing_turns_in_a_row(tmp_path: Path) -> None:
    # One bad turn is a bad turn; three in a row is a pattern, which is the whole
    # difference the error_streak threshold draws.
    gate = _gate(tmp_path, says('{"action": "noop"}'))
    for _ in range(2):
        _turn(gate, [_started(), _failure(), _finished(FINE)])
    assert LAST[-1].call_count == 0
    assert gate.streak == 2
    _turn(gate, [_started(), _failure(), _finished(FINE)])
    assert LAST[-1].call_count == 1
    _turn(gate, [_started(), _finished(FINE)])  # a clean turn, and the streak is over
    assert gate.streak == 0


def test_an_answer_that_is_not_one_of_the_eight_is_rejected_and_logged(tmp_path: Path) -> None:
    # `learn` is the one ADR-0017 took away, so it is the one worth naming here.
    gate = _gate(tmp_path, says('{"action": "learn", "text": "the user prefers tabs"}'))
    seen = _acted(gate)
    _turn(gate, [_started(), _finished(HUGE)])
    assert gate.store.mutations() == []
    logged = gate.store.rejections()
    assert len(logged) == 1 and "learn" in logged[0][3]
    assert [event.action for event in seen] == ["rejected"]


def test_a_proposal_to_loosen_policy_is_rejected_and_logged(tmp_path: Path) -> None:
    gate = _gate(tmp_path, says('{"action": "tighten_policy", "mode": "yolo"}'))
    _turn(gate, [_started(), _finished(HUGE)])
    assert gate.guard.base.mode == "auto"
    assert len(gate.store.rejections()) == 1


def test_a_tightening_reaches_the_live_guard_and_nothing_else(tmp_path: Path) -> None:
    gate = _gate(tmp_path, says('{"action": "tighten_policy", "mode": "read-only"}'))
    _turn(gate, [_started(), _finished(HUGE)])
    assert gate.guard.base.mode == "read-only"
    # In memory only: the guard changed, and no configuration file was written
    # [PERM-8, CTRL-12].
    assert not (tmp_path / "config.toml").exists()


def test_a_controller_that_explodes_never_reaches_the_turn(tmp_path: Path) -> None:
    # CTRL-11, the one that matters: the request raises, and the turn that already
    # finished does not care. The failure becomes a row, not an exception.
    gate = _gate(tmp_path, ScriptedResponse(raises=RuntimeError("no host")))
    _turn(gate, [_started(), _finished(HUGE)])
    logged = gate.store.rejections()
    assert len(logged) == 1 and "no host" in logged[0][3]


def test_a_subagents_turn_is_not_the_gates_business(tmp_path: Path) -> None:
    gate = _gate(tmp_path, says('{"action": "noop"}'), config=_config(mode="always"))
    _turn(gate, [replace(_finished(HUGE), agent_id="sub", depth=1)])
    assert LAST[-1].call_count == 0


def test_attach_does_nothing_at_all_unless_the_controller_is_switched_on(tmp_path: Path) -> None:
    # The default is off, and that is the positioning rather than timidity: a
    # harness that promises no hidden calls does not start making one per turn.
    bus = EventBus()
    guard = Guard(Policy(mode="auto", cwd=tmp_path, home=tmp_path))
    assert attach(bus, root=tmp_path, home=tmp_path, config=Config(), guard=guard) is None
    _turn_is_ignored(bus)
    assert attach(bus, root=tmp_path, home=tmp_path, config=_config(), guard=guard) is not None


def _turn_is_ignored(bus: EventBus) -> None:
    # Nothing subscribed means a turn passes through the bus with no effect at all;
    # emitting one is a better proof of that than reading the subscriber list.
    bus.emit(_finished(HUGE))


def test_overrides_of_a_project_that_never_ran_the_controller_is_empty(tmp_path: Path) -> None:
    assert overrides(tmp_path) == {}
    assert not (tmp_path / ".edgar" / "controller.db").exists()
