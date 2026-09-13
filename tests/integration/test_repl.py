"""The REPL, driven through `Shell` with the fake provider [CLI-12, CLI-13, CLI-24, CLI-27, CLI-28].

Each test types lines the way a user would, while turns run, and asserts on what
was printed, the events and the transcript. The terminal wiring has its own test
at the end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any

import pytest
from harness import Recorder, slow_registry, tool_use

from edgar.cli import repl
from edgar.cli.render import Printer, Renderer
from edgar.cli.repl import Shell
from edgar.cli.statusbar import Status
from edgar.config.schema import Config, ModelSection
from edgar.core.events import (
    AsideFinished,
    EventBus,
    InputQueued,
    ModelSelected,
    SteerApplied,
    TurnFinished,
)
from edgar.core.loop import Runtime
from edgar.core.message import ToolResultBlock
from edgar.core.session import Session
from edgar.core.units import pairing_violations
from edgar.providers.fake import FakeProvider, ScriptedResponse


class Rig:
    def __init__(self, root: Path, steps: Sequence[ScriptedResponse] | None, answers: list[str]):
        self.out: list[str] = []
        self.recorder = Recorder()
        self.provider = FakeProvider(steps)
        bus = EventBus()
        printer = Printer(self.out.append, color=False, width=lambda: 80)
        renderer = Renderer(printer)
        status = Status("fake/test")
        for subscriber in (renderer, status, self.recorder):
            bus.subscribe(subscriber)
        rt = Runtime(self.provider, "test", slow_registry(), "system", bus, name="fake/test")
        self.answers = answers

        async def ask(question: str) -> str:
            self.out.append(question)
            return self.answers.pop(0)

        self.shell = Shell(
            config=Config(model=ModelSection(default="fake/test")),
            root=root,
            env={},
            session=Session(cwd=root, model="fake/test", mode="read-only"),
            rt=rt,
            renderer=renderer,
            status=status,
            ask=ask,
        )

    @property
    def text(self) -> str:
        return "".join(self.out)

    async def type(self, *lines: str) -> None:
        for line in lines:
            await self.shell.handle(line)

    async def settle(self) -> None:
        """Until no turn, queued input or aside is left."""
        while self.shell.busy or self.shell.queue or self.shell.asides:
            await asyncio.sleep(0.005)


Scenario = Callable[[Rig], Coroutine[Any, Any, None]]


def play(
    root: Path,
    scenario: Scenario,
    steps: Sequence[ScriptedResponse] | None = None,
    answers: list[str] | None = None,
) -> Rig:
    rig = Rig(root, steps, answers or [])
    asyncio.run(scenario(rig))
    return rig


def slow(seconds: float = 0.2) -> ScriptedResponse:
    return ScriptedResponse(tool_calls=[tool_use("slow", {"seconds": seconds}, id="tu_slow")])


def test_a_prompt_runs_a_turn_and_streams_its_text(tmp_project: Path) -> None:
    async def scenario(r: Rig) -> None:
        await r.type("read a.txt")
        await r.settle()

    r = play(tmp_project, scenario)
    assert '· read {"path": "a.txt"}' in r.text
    assert "hello" in r.text and r.shell.session.title == "read a.txt"


def test_text_typed_during_a_turn_is_queued_and_runs_after_it(tmp_project: Path) -> None:
    steps = [slow(), ScriptedResponse(text="first done"), ScriptedResponse(text="second done")]

    async def scenario(r: Rig) -> None:
        await r.type("first")
        await asyncio.sleep(0.02)
        await r.type("second")
        assert list(r.shell.queue) == ["second"] and r.shell.status.queued == 1
        await r.settle()

    r = play(tmp_project, scenario, steps)
    assert [e.text for e in r.recorder.of(InputQueued)] == ["second"]
    users = [m.text for m in r.shell.session.transcript if m.role == "user"]
    assert users == ["first", "second"]
    assert r.text.index("first done") < r.text.index("second done")


def test_a_steer_lands_between_units_and_the_turn_goes_on(tmp_project: Path) -> None:
    steps = [slow(), ScriptedResponse(text="adjusted")]

    async def scenario(r: Rig) -> None:
        await r.type("work")
        await asyncio.sleep(0.02)  # the slow tool is running
        await r.type("/steer use src/ instead")
        await r.settle()

    r = play(tmp_project, scenario, steps)
    roles = [(m.role, m.meta.get("via")) for m in r.shell.session.transcript]
    assert roles == [
        ("user", None),
        ("assistant", None),
        ("tool", None),
        ("user", "steer"),
        ("assistant", None),
    ]
    assert [e.text for e in r.recorder.of(SteerApplied)] == ["use src/ instead"]
    assert pairing_violations(r.shell.session.transcript) == []


def test_stop_mid_tool_call_seals_the_transcript_and_gives_back_the_queue(
    tmp_project: Path,
) -> None:
    async def scenario(r: Rig) -> None:
        await r.type("work")
        await asyncio.sleep(0.02)
        await r.type("next thing", "/steer not delivered", "/stop")
        await r.settle()

    r = play(tmp_project, scenario, [slow(5.0)])
    transcript = r.shell.session.transcript
    assert pairing_violations(transcript) == []
    (result,) = transcript[-1].tool_results
    assert isinstance(result, ToolResultBlock) and result.error is not None
    assert (result.text, result.error.kind) == ("cancelled by user", "cancelled")
    assert r.shell.pending_input == "next thing\nnot delivered"  # back on the input line
    assert r.recorder.of(TurnFinished)[-1].reason == "cancelled"
    assert "cancelled" in r.text


def test_stop_mid_stream_keeps_the_partial_text_marked_interrupted(tmp_project: Path) -> None:
    streaming = ScriptedResponse(text="half an answer", stream_chunks=2, stall_s=5.0)

    async def scenario(r: Rig) -> None:
        await r.type("go")
        await asyncio.sleep(0.02)
        await r.type("/stop")
        await r.settle()

    r = play(tmp_project, scenario, [streaming])
    last = r.shell.session.transcript[-1]
    assert (last.role, last.text, last.meta) == ("assistant", "half an", {"interrupted": True})


def test_pause_holds_at_the_safe_point_and_resume_continues(tmp_project: Path) -> None:
    steps = [slow(0.05), ScriptedResponse(text="finished")]

    async def scenario(r: Rig) -> None:
        await r.type("work")
        await asyncio.sleep(0.01)
        await r.type("/pause")
        await asyncio.sleep(0.2)  # the tool call finishes; the next request waits
        assert r.provider.call_count == 1 and r.shell.busy
        await r.type("/status")
        await r.type("/resume")
        await r.settle()

    r = play(tmp_project, scenario, steps)
    assert r.provider.call_count == 2 and "finished" in r.text
    assert "turn          paused" in r.text
    assert [e.name for e in r.recorder.events if e.name in ("Paused", "Resumed")] == [
        "Paused",
        "Resumed",
    ]


def test_btw_answers_on_the_side_and_leaves_the_transcript_alone(tmp_project: Path) -> None:
    steps = [ScriptedResponse(text="the turn"), ScriptedResponse(text="a side answer")]

    async def scenario(r: Rig) -> None:
        await r.type("hello")
        await r.settle()
        before = list(r.shell.session.transcript)
        await r.type("/btw what does this regex do?")
        await r.settle()
        assert r.shell.session.transcript == before

    r = play(tmp_project, scenario, steps)
    (answer,) = r.recorder.of(AsideFinished)
    assert answer.answer == "a side answer"
    assert "── btw ──\na side answer" in r.text
    assert r.provider.requests[1][-1].text == "what does this regex do?"


def test_model_switches_for_the_rest_of_the_session(tmp_project: Path) -> None:
    async def scenario(r: Rig) -> None:
        await r.type("/model fake/test", "/model nowhere/x")

    r = play(tmp_project, scenario)
    (selected,) = r.recorder.of(ModelSelected)
    assert (selected.model, selected.rule) == ("fake/test", "user")
    assert "unknown provider 'nowhere'" in r.text


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("/help", "/steer"),
        ("/undo 2", "/undo arrives in M5"),
        ("/frobnicate", "unknown command /frobnicate"),
        ("/mode auto", "mode: auto"),
        ("/mode yolo", "arrives in M3"),
        ("/title my work", "title: my work"),
        ("/cost", "session cost: $0.0000"),
        ("/queue", "queue empty"),
        ("/stop", "nothing is running"),
        ("/thinking", "reasoning shown"),
        ("/new", "new session"),
    ],
)
def test_commands(tmp_project: Path, line: str, expected: str) -> None:
    async def scenario(r: Rig) -> None:
        await r.type(line)

    assert expected in play(tmp_project, scenario).text


def test_quit(tmp_project: Path) -> None:
    async def scenario(r: Rig) -> None:
        await r.type("/quit")
        assert r.shell.done

    play(tmp_project, scenario)


def test_the_terminal_wiring(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """prompt_toolkit reads the lines; output goes above the prompt."""
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    out: list[str] = []
    monkeypatch.setattr(repl, "_write", out.append)

    async def scenario() -> int:
        # An app session with a pipe and a dummy screen: no real console needed,
        # which Windows CI does not have.
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            task = asyncio.create_task(
                repl.interact(
                    cwd=tmp_project, model="fake/test", mode="read-only", env={}, home=home
                )
            )
            pipe.send_text("read a.txt\r")
            for _ in range(200):
                if "world" in "".join(out):
                    break
                await asyncio.sleep(0.01)
            pipe.send_text("/quit\r")
            return await asyncio.wait_for(task, 5)

    assert asyncio.run(scenario()) == 0
    text = "".join(out)
    assert "edgar " in text and "hello" in text and "world" in text
    assert (home / ".edgar" / "history").read_text(encoding="utf-8").count("read a.txt") == 1
