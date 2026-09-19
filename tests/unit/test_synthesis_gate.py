"""Journey J8, driven through the gate with the scripted provider [SKL-8..12, SKL-16].

J8's four acceptance lines, one test each and then some:

  a turn that ends with a failing check produces no skill
  a verified turn over the thresholds produces exactly one proposal
  the synthesiser's input contains no tool output
  in `auto` mode no hand-authored skill file changes  (the property test too)

The model is the scripted fake, so the "skill" below is fabricated text. What is
under test is everything around it: whether a call happens at all, what that call
is allowed to carry, where the answer is allowed to land.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
from scripted import ScriptedProvider, ScriptedResponse

import edgar.controller.gate as gate_module
from edgar.config.schema import Config, ControllerSection, ModelSection, SkillsSection
from edgar.controller.gate import Gate
from edgar.controller.store import Controls
from edgar.core.events import (
    Event,
    EventBus,
    PromptSteered,
    PromptTyped,
    SkillsActivated,
    ToolFinished,
    TurnFinished,
    TurnStarted,
    VerifyFinished,
)
from edgar.core.message import ErrorRecord
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy
from edgar.providers.base import Usage
from edgar.skills.discovery import discover

Mode = Literal["off", "propose", "auto"]
FINE = Usage(input_tokens=10, output_tokens=10)  # nothing the controller cares about

# A body of the shape SKL-16 demands. Anything else is refused before it is written.
GOOD = "\n".join(
    [
        "## When to use",
        "When a pinned dependency has to move and the tests have to follow.",
        "## Procedure",
        "1. Edit the pin. 2. Run the check. 3. Fix what it says.",
        "## Pitfalls",
        "The first failure is rarely the only one.",
        "## Verification",
        "The declared check passes.",
    ]
)
SKILL = json.dumps(
    {
        "action": "propose_skill",
        "name": "dependency-bump",
        "body": GOOD,
        "reason": "eleven calls and a passing check",
    }
)

LAST: list[ScriptedProvider] = []


@pytest.fixture(autouse=True)
def _no_real_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_resolve(model: str, config: Any = None, **kw: Any) -> tuple[Any, str]:
        return LAST[-1], "test"

    monkeypatch.setattr(gate_module, "resolve", fake_resolve)
    LAST.clear()


def _config(mode: Mode = "propose", **skills: Any) -> Config:
    return replace(
        Config(),
        model=ModelSection(default="fake/test"),
        controller=ControllerSection(enabled=True),
        skills=SkillsSection(synthesis=mode, **skills),
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
        session="0f3a1c",
        window=10_000,
    )


def _turn(gate: Gate, events: Iterable[Event]) -> None:
    # Same shape as test_controller_gate.py: the bus is synchronous, the gate's own
    # call is not, so the loop is given a few turns to let the task finish.
    async def go() -> None:
        for event in events:
            gate(event)
        for _ in range(8):
            await asyncio.sleep(0)

    asyncio.run(go())


def _run(*, ok: bool = True, tools: int = 11, error: bool = True) -> list[Event]:
    """J8's run: a typed line, eleven calls, two failures, a declared check."""
    events: list[Event] = [
        PromptTyped(text="bump the httpx pin and fix whatever breaks"),
        TurnStarted(turn_id="t1", model="fake/test"),
    ]
    record = ErrorRecord(tool="shell", kind="nonzero_exit", exit_code=1, program="pytest")
    for index in range(tools):
        bad = error and index in (3, 4)
        events.append(
            ToolFinished(
                id=f"c{index}",
                tool="edit" if index % 2 else "shell",
                ok=not bad,
                duration_ms=1,
                truncated=False,
                blob=None,
                error=record if bad else None,
            )
        )
    events.append(VerifyFinished(ok=ok, exit_code=0 if ok else 1, attempt=1, duration_ms=1))
    events.append(TurnFinished(turn_id="t1", usage=FINE, cost=0.0, reason="stop"))
    return events


def _proposals(root: Path) -> list[Path]:
    return sorted((root / ".edgar" / "proposals").glob("*.md"))


def _learned(root: Path) -> list[Path]:
    return sorted((root / ".edgar" / "skills" / "learned").rglob("SKILL.md"))


# --- J8's acceptance lines ---------------------------------------------------


def test_a_turn_that_ends_with_a_failing_check_produces_no_skill(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL))
    _turn(gate, _run(ok=False))
    assert LAST[-1].call_count == 0  # no model is asked, so there is nothing to refuse
    assert _proposals(tmp_path) == [] and _learned(tmp_path) == []


def test_a_verified_run_over_the_thresholds_produces_exactly_one_proposal(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL))
    _turn(gate, _run())
    assert LAST[-1].call_count == 1 and LAST[-1].tools_seen == [[]]
    written = _proposals(tmp_path)
    assert len(written) == 1 and "dependency-bump" in written[0].name
    # propose is the default, so nothing is in the index yet [SKL-10].
    assert _learned(tmp_path) == []
    assert [m.action for m in gate.store.mutations()] == ["propose_skill"]


def test_the_synthesisers_input_carries_no_tool_output_and_no_error_text(tmp_path: Path) -> None:
    # The gate never receives tool output, so the assertion is about what it does
    # with what it does receive: names in call order, the four computed fields, the
    # typed line. Nothing renders an error's message because there is no message.
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL))
    _turn(gate, _run())
    sent = LAST[-1].requests[0][0].text
    assert "bump the httpx pin" in sent  # the typed line: the one safe road [MEM-8]
    assert "tools called, in order: shell, edit" in sent
    assert "shell nonzero_exit exit 1 (pytest)" in sent
    assert "declared check: passed" in sent
    assert "what tripped: long, recovered" in sent


def test_auto_writes_into_the_machine_owned_folder_and_the_index_sees_it(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL), config=_config("auto"))
    _turn(gate, _run())
    written = _learned(tmp_path)
    assert len(written) == 1
    assert (
        written[0].relative_to(tmp_path).as_posix()
        == ".edgar/skills/learned/dependency-bump/SKILL.md"
    )
    text = written[0].read_text(encoding="utf-8")
    assert (
        "learned: true" in text and "session: 0f3a1c" in text and "trigger: long,recovered" in text
    )
    # The next session sees it, tagged, which is the second half of J8 [SKL-12].
    found = discover(tmp_path, tmp_path).skills["dependency-bump"]
    assert found.origin == "project learned"


def test_auto_without_a_passing_check_never_writes_a_file(tmp_path: Path) -> None:
    # Belt and braces: the trigger already refuses this, so the run below is the one
    # trigger that does not need a check — a human correction [SKL-8c, SKL-11].
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL), config=_config("auto"))
    _turn(
        gate,
        [
            PromptTyped(text="bump the httpx pin"),
            PromptSteered(text="no, pin it to the minor version"),
            TurnStarted(turn_id="t1", model="fake/test"),
            TurnFinished(turn_id="t1", usage=FINE, cost=0.0, reason="stop"),
        ],
    )
    assert LAST[-1].call_count == 1  # the correction tripped it
    assert _learned(tmp_path) == []
    assert len(_proposals(tmp_path)) == 1


# --- the rest of the machinery ----------------------------------------------


def test_off_is_off_before_anything_is_imported(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL), config=_config("off"))
    _turn(gate, _run())
    assert LAST[-1].call_count == 0


def test_a_turn_that_already_loaded_a_skill_does_not_repeat_itself(tmp_path: Path) -> None:
    # Trigger (d) only. Three tools is under min_tool_calls and nothing failed, so
    # the only way this could fire is the repeat — and a loaded skill stops it.
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL), config=_config(min_repeats=0))
    events = _run(tools=3, error=False)
    events.insert(1, SkillsActivated(names=("dependency-bump",)))
    _turn(gate, events)
    assert LAST[-1].call_count == 0


def test_an_answer_that_is_not_a_skill_is_announced_and_written_nowhere(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(text='{"action": "abort", "reason": "I disapprove"}'))
    _turn(gate, _run())
    assert gate.guard.base.mode == "auto"  # the abort did not happen
    assert _proposals(tmp_path) == [] and _learned(tmp_path) == []


def test_a_synthesiser_that_explodes_never_reaches_the_turn(tmp_path: Path) -> None:
    gate = _gate(tmp_path, ScriptedResponse(raises=RuntimeError("no host")))
    _turn(gate, _run())
    logged = gate.store.rejections()
    assert len(logged) == 1 and "no host" in logged[0][3]


def test_a_hand_authored_skill_of_the_same_name_is_refused_and_left_alone(tmp_path: Path) -> None:
    # The refusal J8's last line generalises. The file is read before and after, so
    # "left alone" means the bytes, not the absence of an exception [SKL-11].
    hand = tmp_path / ".edgar" / "skills" / "dependency-bump" / "SKILL.md"
    hand.parent.mkdir(parents=True)
    hand.write_text(
        "---\nname: dependency-bump\ndescription: mine\n---\n\nmine\n", encoding="utf-8"
    )
    before = hand.read_bytes()
    gate = _gate(tmp_path, ScriptedResponse(text=SKILL), config=_config("auto"))
    _turn(gate, _run())
    assert hand.read_bytes() == before
    assert _learned(tmp_path) == []
    proposal = _proposals(tmp_path)[0].read_text(encoding="utf-8")
    assert "a hand-authored skill has that name" in proposal
