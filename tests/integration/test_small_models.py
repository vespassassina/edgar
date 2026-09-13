"""A small local model that gets the syntax wrong still finishes the work [PRV-16].

M2's done criterion: a model that writes its tool calls inside code fences, or as
plain JSON on a server with no native tools, completes the fake-task set through
the real OpenAI-compatible adapter, with each repair announced.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from harness import Recorder
from wire import Reply, openai_sse

from edgar.config.schema import Config, ProviderSection
from edgar.core.events import EventBus, ToolCallRepaired
from edgar.core.loop import Runtime, run_turn
from edgar.core.session import Session
from edgar.core.units import pairing_violations
from edgar.providers.registry import resolve
from edgar.tools.registry import core_registry

# prompt → what the final answer must contain
TASKS = [
    ("read a.txt", "hello"),
    ("ls src", "main.py"),
    ("read missing.txt", "no such file"),  # a failed call comes back; the model reports it
]


class SmallModel(httpx.AsyncBaseTransport):
    """Knows what to do, writes it badly. On the wire, like Ollama."""

    def __init__(self, style: str) -> None:
        self.style = style

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        last = json.loads(request.content)["messages"][-1]
        if last["role"] in ("tool",) or last["content"].startswith("Tool result:"):
            text = "Done. " + last["content"].removeprefix("Tool result:").strip()
        else:
            verb, _, path = last["content"].partition(" ")
            call = json.dumps({"name": verb, "arguments": {"path": path}})
            text = f"```json\n{call}\n```" if self.style == "fence" else f"Sure. {call}"
        body = openai_sse(Reply(text=text), "ollama")
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


@pytest.mark.parametrize(("style", "native"), [("fence", True), ("text-call", False)])
def test_a_fumbling_model_completes_the_fake_tasks(
    tmp_project: Path, style: str, native: bool
) -> None:
    (tmp_project / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    config = Config(providers={"ollama": ProviderSection(native_tools=native)})
    provider, model = resolve("ollama/small", config, env={}, transport=SmallModel(style))
    recorder, bus = Recorder(), EventBus()
    bus.subscribe(recorder)
    runtime = Runtime(provider, model, core_registry(), "You are helpful.", bus)

    for prompt, expected in TASKS:
        session = Session(cwd=tmp_project, model="ollama/small", mode="read-only")
        result = asyncio.run(run_turn(session, prompt, runtime))
        assert expected in result.text, prompt
        assert pairing_violations(session.transcript) == []
    repairs = recorder.of(ToolCallRepaired)
    assert [r.repair for r in repairs] == [style] * len(TASKS)
