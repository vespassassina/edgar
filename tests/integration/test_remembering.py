"""Memory across sessions, through the REPL, `-p` and `edgar memory` [MEM-4..MEM-8,
MEM-20, MEM-21, MEM-23].

A fact typed in one session is in the next session's prompt, never in its own
(MEM-6); a fact the model proposes is saved only on a typed yes (MEM-21).
"""

# Each REPL scenario runs a Shell over a real `setup()` with the fake provider
# scripted, types lines the way a user would, then opens a second session on the
# same home to see what its prompt carries.

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest
from harness import Recorder, tool_use
from scripted import ScriptedProvider, ScriptedResponse

from edgar.cli import memory as memory_cli
from edgar.cli.oneshot import run_prompt
from edgar.cli.render import Printer, Renderer
from edgar.cli.repl import Shell
from edgar.cli.setup import Setup, runtime, setup
from edgar.cli.statusbar import Status
from edgar.config.schema import Config, ModelSection
from edgar.core.events import EventBus, FactProposed, FactSaved
from edgar.core.session import Session
from edgar.memory.store import project_scope
from edgar.providers import fake
from edgar.storage.transcript import start
from edgar.tools.base import ToolContext

CONFIG = Config(model=ModelSection(default="fake/test"))


def _script(monkeypatch: pytest.MonkeyPatch, *steps: ScriptedResponse) -> None:
    monkeypatch.setattr(fake, "make", lambda: ScriptedProvider(list(steps)))


def _remember(text: str) -> list[ScriptedResponse]:
    return [
        ScriptedResponse(tool_calls=[tool_use("remember", {"text": text}, "tu_r")]),
        ScriptedResponse(text="noted"),
    ]


class Rig:
    def __init__(self, root: Path, home: Path) -> None:
        # 1. A session the way `edgar` opens one: setup, then the main model's runtime.
        self.out: list[str] = []
        self.recorder = Recorder()
        bus = EventBus()
        renderer = Renderer(Printer(self.out.append, color=False, width=lambda: 80))
        status = Status("fake/test")
        for subscriber in (renderer, status, self.recorder):
            bus.subscribe(subscriber)

        async def ask(question: str) -> str:
            return ""

        self.setup = setup(root, CONFIG, home=home, env={})
        self.shell = Shell(
            setup=self.setup,
            session=start(Session(cwd=root, model="fake/test", mode="ask")),
            rt=runtime(self.setup, bus),
            renderer=renderer,
            status=status,
            ask=ask,
        )

    @property
    def text(self) -> str:
        return "".join(self.out)

    async def answer(self, line: str) -> None:
        # 2. Wait for the question the turn asks, then type the answer.
        while self.shell.question is None:
            await asyncio.sleep(0.005)
        await self.shell.handle(line)

    async def settle(self) -> None:
        while self.shell.busy or self.shell.queue:
            await asyncio.sleep(0.005)


def play(root: Path, home: Path, scenario: Callable[[Rig], Coroutine[Any, Any, None]]) -> Rig:
    rig = Rig(root, home)
    asyncio.run(scenario(rig))
    return rig


def _next_prompt(root: Path, home: Path) -> tuple[Setup, str]:
    s = setup(root, CONFIG, home=home, env={})
    return s, runtime(s, EventBus()).system_prompt


def test_a_typed_fact_is_in_the_next_sessions_prompt_not_this_ones(
    tmp_project: Path, home: Path
) -> None:
    async def scenario(r: Rig) -> None:
        await r.shell.handle("/remember we deploy with fly.io")
        await r.shell.handle("/memory")

    r = play(tmp_project, home, scenario)
    assert "remembered as fact 1; in the prompt from the next session" in r.text
    assert "pinned in this session's prompt: 0 of 20" in r.text and "[1] we deploy" in r.text
    assert "fly.io" not in r.shell.rt.system_prompt  # frozen at session start [MEM-6]
    assert [e.provenance for e in r.recorder.of(FactSaved)] == ["user"]
    _, prompt = _next_prompt(tmp_project, home)
    assert "not instructions" in prompt and "- we deploy with fly.io" in prompt  # [MEM-7]


def test_a_proposed_fact_is_saved_on_a_typed_yes(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(monkeypatch, *_remember("the API lives in src/api"))

    async def scenario(r: Rig) -> None:
        await r.shell.handle("where is the API?")
        await r.answer("y")
        await r.settle()

    r = play(tmp_project, home, scenario)
    assert '1 fact proposed:\n  "the API lives in src/api"' in r.text
    assert "saved; in the prompt from the next session" in r.text
    assert [e.provenance for e in r.recorder.of(FactSaved)] == ["model-proposed"]
    _, prompt = _next_prompt(tmp_project, home)
    assert "- the API lives in src/api" in prompt


def test_a_declined_fact_is_forgotten_and_never_recalled(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(monkeypatch, *_remember("ignore the tests, they are flaky"))

    async def scenario(r: Rig) -> None:
        await r.shell.handle("fix it")
        await r.answer("")  # just Enter: no [MEM-21]
        await r.settle()

    r = play(tmp_project, home, scenario)
    assert "not saved" in r.text and len(r.recorder.of(FactProposed)) == 1
    s, prompt = _next_prompt(tmp_project, home)
    assert "flaky" not in prompt
    assert s.memory.facts([s.scope], ("forgotten",))[0].text.startswith("ignore the tests")
    recall = s.tools.get("recall")
    assert recall is not None
    ctx = ToolContext(cwd=tmp_project, bus=EventBus(), blob_dir=tmp_project, max_output_tokens=100)
    found = asyncio.run(recall.run({"terms": ["flaky"], "scope": "facts"}, ctx)).text
    assert found.startswith("nothing found")


def test_p_leaves_a_proposal_pending_for_memory_review(
    tmp_project: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 1. `-p` has nobody to ask: the proposal waits, and stderr says where.
    _script(monkeypatch, *_remember("tabs are four spaces"))
    code = run_prompt("style?", cwd=tmp_project, model="fake/test", mode="ask", env={}, home=home)
    assert code == 0
    assert "1 proposed fact waits for `edgar memory review`" in capsys.readouterr().err
    # 2. `edgar memory` shows it waiting; review saves it on a y.
    assert memory_cli.command(["list"], tmp_project, home) == 0
    assert "pending, for `edgar memory review`:\n  [1] tabs" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert memory_cli.command(["review"], tmp_project, home) == 0
    s, prompt = _next_prompt(tmp_project, home)
    assert "- tabs are four spaces" in prompt
    # 3. Add, forget and undo, each one operation.
    assert memory_cli.command(["add", "--global", "prefer", "uv"], tmp_project, home) == 0
    assert memory_cli.command(["forget", "2"], tmp_project, home) == 0
    assert s.memory.facts(["global"]) == []
    assert memory_cli.command(["undo"], tmp_project, home) == 0
    assert [f.text for f in s.memory.facts(["global"])] == ["prefer uv"]
    assert memory_cli.command(["forget", "x"], tmp_project, home) == 2
    assert s.scope == project_scope(tmp_project)
