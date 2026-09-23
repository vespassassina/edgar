"""The turn loop with the fake provider. Asserting on the event sequence states the
intended behaviour most directly."""

from __future__ import annotations

from pathlib import Path

import pytest
from harness import Recorder, new_session, run_turn_sync, runtime, scripted, tool_use
from scripted import ScriptedProvider, ScriptedResponse

from edgar.core.errors import ProviderError
from edgar.core.events import Escalation, Event, Fallback, SteerApplied, TextDelta, ToolProposed
from edgar.core.units import pairing_violations
from edgar.providers.escalation import EscalationState, Triggers


class _OtherFamily(ScriptedProvider):
    family = "other"  # a fallback that crosses provider families [PRV-13]


def test_loop_executes_tool_and_continues(tmp_project: Path, recorder: Recorder) -> None:
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("read", {"path": "a.txt"})]),
        ScriptedResponse(text="The file says hello."),
    )
    session = new_session(tmp_project)
    result = run_turn_sync(session, "what's in a.txt?", runtime(provider, recorder))

    assert result.text == "The file says hello."
    assert provider.call_count == 2
    assert recorder.names == [
        "TurnStarted",
        "RequestStarted",
        "RequestFinished",
        "ToolProposed",
        "PermissionResolved",
        "ToolStarted",
        "ToolFinished",
        "RequestStarted",
        "TextDelta",
        "RequestFinished",
        "TurnFinished",
    ]
    second_request = provider.requests[1]
    assert second_request[0].role == "system"
    assert "hello" in second_request[-1].tool_results[0].text
    assert pairing_violations(session.transcript) == []


def test_denied_tool_reports_to_model(tmp_project: Path, recorder: Recorder) -> None:
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("read", {"path": "../outside.txt"})]),
        ScriptedResponse(text="I cannot read that."),
    )
    session = new_session(tmp_project)
    run_turn_sync(session, "read the file next door", runtime(provider, recorder))

    assert recorder.names == [
        "TurnStarted",
        "RequestStarted",
        "RequestFinished",
        "ToolProposed",
        "PermissionResolved",  # denied
        "RequestStarted",
        "TextDelta",
        "RequestFinished",
        "TurnFinished",
    ]
    result = session.transcript[2].tool_results[0]
    assert result.is_error and result.error is not None
    assert result.error.kind == "permission_denied"


def test_several_calls_in_one_response_run_in_order(tmp_project: Path, recorder: Recorder) -> None:
    calls = [
        tool_use("read", {"path": "a.txt"}, id="tu_1"),
        tool_use("ls", {}, id="tu_2"),
        tool_use("read", {"path": "missing.txt"}, id="tu_3"),
    ]
    provider = scripted(ScriptedResponse(tool_calls=calls), ScriptedResponse(text="done"))
    session = new_session(tmp_project)
    run_turn_sync(session, "look around", runtime(provider, recorder))

    started = [e.id for e in recorder.of(ToolProposed)]
    assert started == ["tu_1", "tu_2", "tu_3"]
    results = session.transcript[2].tool_results
    assert [r.tool_use_id for r in results] == ["tu_1", "tu_2", "tu_3"]
    assert [r.is_error for r in results] == [False, False, True]


def test_a_steer_lands_between_units_and_keeps_the_turn_going(
    tmp_project: Path, recorder: Recorder
) -> None:
    session = new_session(tmp_project)

    def steer_during_first_request(event: Event) -> None:
        if isinstance(event, TextDelta) and event.text == "first answer":
            session.steer("actually, list the files")

    rt = runtime(scripted(*[ScriptedResponse(text=t) for t in ("first answer", "ok")]), recorder)
    rt.bus.subscribe(steer_during_first_request)
    result = run_turn_sync(session, "hello", rt)

    assert result.text == "ok"
    assert [e.text for e in recorder.of(SteerApplied)] == ["actually, list the files"]
    roles = [m.role for m in session.transcript]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert session.transcript[2].meta == {"via": "steer"}


def test_a_steer_during_a_tool_call_waits_for_the_result(
    tmp_project: Path, recorder: Recorder
) -> None:
    session = new_session(tmp_project)

    def steer_while_tool_runs(event: Event) -> None:
        if event.name == "ToolStarted":
            session.steer("also check src/")

    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("read", {"path": "a.txt"})]),
        ScriptedResponse(text="done"),
    )
    rt = runtime(provider, recorder)
    rt.bus.subscribe(steer_while_tool_runs)
    run_turn_sync(session, "read a.txt", rt)

    assert [m.role for m in session.transcript] == [
        "user",
        "assistant",
        "tool",
        "user",
        "assistant",
    ]
    assert pairing_violations(session.transcript) == []


def test_provider_errors_propagate(tmp_project: Path) -> None:
    provider = scripted(ScriptedResponse(raises=ProviderError("rate limited")))
    with pytest.raises(ProviderError):
        run_turn_sync(new_session(tmp_project), "hi", runtime(provider))


def test_a_provider_error_falls_back_to_the_next_model(
    tmp_project: Path, recorder: Recorder
) -> None:  # [ROUTE-7]
    primary = scripted(ScriptedResponse(raises=ProviderError("rate limited")))
    secondary = scripted(ScriptedResponse(text="from the fallback"))
    rt = runtime(
        primary, recorder, name="primary/test", fallback=(("secondary/test", secondary, "test"),)
    )
    result = run_turn_sync(new_session(tmp_project), "hi", rt)

    assert result.text == "from the fallback"
    assert secondary.call_count == 1
    fell_back = recorder.of(Fallback)
    assert len(fell_back) == 1 and fell_back[0].from_model == "primary/test"
    assert fell_back[0].to_model == "secondary/test"
    assert recorder.names.count("RequestStarted") == 2
    assert recorder.names.count("RequestFinished") == 1  # only the request that succeeded


def test_a_fallback_across_families_drops_reasoning(tmp_project: Path) -> None:  # [PRV-13]
    primary = scripted(ScriptedResponse(raises=ProviderError("down")))
    secondary = _OtherFamily([ScriptedResponse(text="ok")])
    rt = runtime(primary, name="a/test", fallback=(("b/test", secondary, "test"),))
    run_turn_sync(new_session(tmp_project), "hi", rt)

    assert secondary.reasoning_used == [False]


def test_fallback_is_exhausted_when_nothing_covers_the_turn(tmp_project: Path) -> None:
    original = ProviderError("rate limited")
    primary = scripted(ScriptedResponse(raises=original))
    already_tried = scripted()  # empty script: would raise "exhausted" if ever called
    rt = runtime(primary, name="a/test", fallback=(("a/test", already_tried, "test"),))
    with pytest.raises(ProviderError, match="rate limited"):
        run_turn_sync(new_session(tmp_project), "hi", rt)


def test_escalation_moves_up_the_chain_on_repeated_tool_failure(
    tmp_project: Path, recorder: Recorder
) -> None:  # [ROUTE-5, ROUTE-10]
    weak = scripted(
        ScriptedResponse(tool_calls=[tool_use("no-such-tool", {})]),
        ScriptedResponse(tool_calls=[tool_use("no-such-tool", {})]),
    )
    stronger = scripted(ScriptedResponse(text="done by the stronger model"))
    state = EscalationState(
        chain=(("b/test", stronger, "b-model"),),
        max_escalations=1,
        on=Triggers(consecutive_failures=2),
    )
    rt = runtime(weak, recorder, name="a/test", escalation=state)
    result = run_turn_sync(new_session(tmp_project), "hi", rt)

    assert result.text == "done by the stronger model"
    assert stronger.call_count == 1
    escalated = recorder.of(Escalation)
    assert len(escalated) == 1
    assert escalated[0].from_model == "a/test"
    assert escalated[0].to_model == "b/test"


def test_escalation_never_runs_past_max_escalations(tmp_project: Path, recorder: Recorder) -> None:
    weak = scripted(
        ScriptedResponse(tool_calls=[tool_use("no-such-tool", {})]),
        ScriptedResponse(tool_calls=[tool_use("no-such-tool", {})]),
        ScriptedResponse(tool_calls=[tool_use("no-such-tool", {})]),
        ScriptedResponse(text="gave up trying"),
    )
    state = EscalationState(chain=(), max_escalations=0, on=Triggers(consecutive_failures=1))
    rt = runtime(weak, recorder, name="a/test", escalation=state)
    run_turn_sync(new_session(tmp_project), "hi", rt)

    assert recorder.of(Escalation) == []


def test_the_rule_based_test_model_reads_a_file(tmp_project: Path) -> None:
    result = run_turn_sync(new_session(tmp_project), "read a.txt", runtime(ScriptedProvider()))
    assert result.text == "     1\thello\n     2\tworld"


def test_usage_adds_up_across_requests(tmp_project: Path) -> None:
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("ls", {})]), ScriptedResponse(text="x" * 40)
    )
    result = run_turn_sync(new_session(tmp_project), "list", runtime(provider))
    assert result.usage.output_tokens == 10
    assert result.usage.input_tokens > 0
