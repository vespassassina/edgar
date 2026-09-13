"""The rig every contract test drives: one provider, one scenario, one transport.

Offline, the transport replays the scenario's cassette; the user-defined provider
talks to a real server on loopback instead. `--live` sends the same requests to
the real APIs, and `--record PROVIDER` also writes what came back. Loaded as a
pytest plugin by tests/conftest.py, which is what makes `rig` a fixture.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import cassettes
import pytest
from cassettes import Captured, Recording, Replay
from fixture_server import FixtureServer
from harness import Recorder

from edgar.config.schema import Config, ProviderSection
from edgar.core.events import EventBus
from edgar.core.message import Message
from edgar.providers.base import Provider, ProviderResponse
from edgar.providers.registry import resolve
from edgar.tools.base import ToolSchema
from edgar.tools.registry import core_registry

MODELS = {
    "openai": "gpt-5-mini",
    "azure": "gpt-5-mini",  # the deployment name
    "openrouter": "openai/gpt-5-mini",
    "ollama": "qwen3",
    "anthropic": "claude-haiku-4-5",
    "compat": "local-model",
}
KEYS = {
    "OPENAI_API_KEY": "test-key",
    "AZURE_OPENAI_API_KEY": "test-key",
    "OPENROUTER_API_KEY": "test-key",
    "ANTHROPIC_API_KEY": "test-key",
}
TOOLS = core_registry().schemas()


@dataclass
class Rig:
    provider: Provider
    model: str
    requests: list[Captured]
    recorder: Recorder = field(default_factory=Recorder)

    def __post_init__(self) -> None:
        self.bus = EventBus()
        self.bus.subscribe(self.recorder)

    def run(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSchema] = TOOLS,
        reasoning: bool = True,
    ) -> ProviderResponse:
        return asyncio.run(self.call(messages, tools=tools, reasoning=reasoning))

    async def call(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSchema] = TOOLS,
        reasoning: bool = True,
    ) -> ProviderResponse:
        return await self.provider.stream(
            messages, tools, model=self.model, bus=self.bus, reasoning=reasoning
        )

    @property
    def body(self) -> Any:
        """The JSON body of the last request sent."""
        return self.requests[-1].body


def config_for(name: str, server: FixtureServer | None, *, replaying: bool = True) -> Config:
    blocks = {"anthropic": {"anthropic": ProviderSection(thinking_budget=1024)}}.get(name, {})
    if name == "azure" and replaying:  # live, the endpoint comes from AZURE_OPENAI_ENDPOINT
        blocks = {"azure": ProviderSection(base_url="https://example.openai.azure.com")}
    if server is not None:
        local = ProviderSection(
            kind="openai-compatible", base_url=server.base_url, stream_usage=True
        )
        blocks = {"local": local}
    return Config(providers=blocks)


@pytest.fixture
def rig(request: pytest.FixtureRequest) -> Iterator[Callable[[str, str], Rig]]:
    live = bool(request.config.getoption("--live"))
    recording: str | None = request.config.getoption("--record")
    cleanup: list[Callable[[], None]] = []

    def make(name: str, scenario: str) -> Rig:
        entry = cassettes.load(name).get(scenario)
        if entry is None:
            pytest.fail(f"no {scenario!r} scenario in tests/cassettes/{name}.json")
        exchanges = entry["exchanges"]
        replaying = scenario in cassettes.UNRECORDABLE or not (live or recording == name)
        if name == "compat":  # always the local fixture server, live or not
            server = FixtureServer(exchanges).__enter__()
            cleanup.append(lambda: server.__exit__(None))
            provider, model = resolve(f"local/{MODELS[name]}", config_for(name, server), env={})
            return Rig(provider, model, server.requests)
        transport: Any = Replay(exchanges)
        if not replaying:
            transport = Recording()
            if recording == name:
                cleanup.append(lambda: cassettes.record(name, scenario, transport.exchanges))
        env = KEYS if replaying else dict(os.environ)
        model_string = f"{name}/{os.environ.get(f'LIVE_MODEL_{name.upper()}', MODELS[name])}"
        config = config_for(name, None, replaying=replaying)
        provider, model = resolve(model_string, config, env=env, transport=transport)
        return Rig(provider, model, transport.requests)

    yield make
    for step in cleanup:
        step()
