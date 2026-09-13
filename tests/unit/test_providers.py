"""Provider resolution, quirks, pricing, routing and the HTTP helpers
[PRV-3, PRV-4, PRV-6, PRV-7, PRV-9, PRV-12, PRV-15, BUD-5, ROUTE-1]."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from cassettes import Replay
from harness import Recorder
from wire import Reply, anthropic_sse, error, ok, openai_sse

from edgar.config.load import load
from edgar.config.schema import Config, ModelSection, PriceSection, ProviderSection
from edgar.context.prompts import choose_profile, load_prompt
from edgar.core.errors import ConfigError, ContextOverflow, EdgarError, ProviderError
from edgar.core.events import EventBus, ProviderRetry
from edgar.core.message import Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock
from edgar.providers.base import Provider, ProviderResponse, Usage
from edgar.providers.http import Retry, _retry_after
from edgar.providers.pricing import BUILTIN, cost_of
from edgar.providers.quirks import QUIRKS, Quirks, quirks_for
from edgar.providers.registry import resolve, split
from edgar.providers.routing import RoutingContext, select_model
from edgar.tools.registry import core_registry

KEYS = {"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k", "OPENROUTER_API_KEY": "k"}
TOOLS = core_registry().schemas()


def run(
    model: str,
    exchanges: list[dict[str, Any]],
    messages: list[Message] | None = None,
    *,
    config: Config | None = None,
    env: dict[str, str] | None = None,
    **options: Any,
) -> tuple[ProviderResponse, Replay, Recorder, Provider]:
    transport = Replay(exchanges)
    provider, name = resolve(
        model, config, env=KEYS if env is None else env, transport=transport, **options
    )
    recorder, bus = Recorder(), EventBus()
    bus.subscribe(recorder)
    messages = messages or [Message("system", (TextBlock("sys"),)), Message.user("hi")]
    response = asyncio.run(provider.stream(messages, TOOLS, model=name, bus=bus))
    return response, transport, recorder, provider


# resolution and config


def test_model_strings_split_at_the_first_slash() -> None:
    assert split("openrouter/openai/gpt-5") == ("openrouter", "openai/gpt-5")
    with pytest.raises(ConfigError, match="provider/model"):
        split("gpt-5")


def test_resolving_imports_only_the_adapter_it_needs(subprocess_env: dict[str, str]) -> None:
    import subprocess
    import sys

    code = (
        "import sys; from edgar.providers.registry import resolve;"
        "resolve('fake/test');"
        "print(sorted(m for m in sys.modules if m.startswith(('httpx', 'edgar.providers.'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=subprocess_env
    )
    assert (
        out.stdout.strip()
        == "['edgar.providers.base', 'edgar.providers.fake', 'edgar.providers.registry']"
    )


def test_a_providers_block_makes_a_new_server_resolvable(tmp_project: Path, home: Path) -> None:
    config_file = tmp_project / ".edgar" / "config.toml"
    config_file.parent.mkdir()
    config_file.write_text(
        '[providers.lmstudio]\nkind = "openai-compatible"\nbase_url = "http://localhost:1234/v1"\n'
        'max_context = 16000\n[pricing."lmstudio/qwen"]\ninput = 0.0\noutput = 0.0\n',
        encoding="utf-8",
    )
    config = load(tmp_project, home=home, env={})
    assert config.providers["lmstudio"].base_url == "http://localhost:1234/v1"
    assert config.origins["providers.lmstudio.max_context"] == str(config_file)
    provider, model = resolve("lmstudio/qwen", config, env={})
    assert (provider.name, model, provider.capabilities.max_context) == ("lmstudio", "qwen", 16000)


@pytest.mark.parametrize(
    ("toml", "expected"),
    [
        ("[providers.x]\nbase_url = 3\n", "[providers.x] base_url must be a string"),
        ('[providers.x]\nkind = "grpc"\n', 'must be one of "openai-compatible", "anthropic"'),
        ("[providers.x]\nnative_tool = false\n", "did you mean native_tools?"),
        ('[pricing."a/b"]\ninput = 1.0\n', '[pricing."a/b"] needs output'),
        ("[providers]\nx = 1\n", "providers.x must be a table"),
    ],
)
def test_provider_and_pricing_blocks_are_validated(
    tmp_project: Path, home: Path, toml: str, expected: str
) -> None:
    path = tmp_project / ".edgar" / "config.toml"
    path.parent.mkdir()
    path.write_text(toml, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load(tmp_project, home=home, env={})
    assert expected in f"{info.value} {info.value.hint}"


def test_blocks_are_set_in_files_not_the_environment(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match=r"config\.toml only"):
        load(tmp_project, home=home, env={"EDGAR_PROVIDERS_X": "1"})


def test_a_new_name_needs_a_kind_and_a_base_url() -> None:
    with pytest.raises(ConfigError, match="unknown provider 'x'"):
        resolve("x/m", Config(providers={"x": ProviderSection(base_url="http://h")}), env={})
    with pytest.raises(ConfigError, match="needs base_url"):
        resolve("x/m", Config(providers={"x": ProviderSection(kind="openai-compatible")}), env={})


def test_a_block_cannot_change_a_builtin_kind() -> None:
    config = Config(providers={"openai": ProviderSection(kind="anthropic")})
    with pytest.raises(ConfigError, match="does not match"):
        resolve("openai/gpt-5", config, env=KEYS)


def test_every_block_key_is_a_quirk_or_says_why_not() -> None:
    quirks = {f.name for f in dataclasses.fields(Quirks)}
    block = {f.name for f in dataclasses.fields(ProviderSection)}
    assert block - quirks == {"kind", "thinking_budget", "prompt_profile"}


def test_block_keys_override_a_builtin_row() -> None:
    quirks = quirks_for(
        "ollama", ProviderSection(base_url="http://gpu:11434/v1", max_context=65536)
    )
    assert (quirks.base_url, quirks.max_context, quirks.cost_source) == (
        "http://gpu:11434/v1",
        65536,
        "free",
    )


def test_no_builtin_row_names_a_host_the_user_did_not_choose() -> None:
    # A provider's own host is chosen by naming the provider; Azure has none to
    # guess, and nothing else is ever contacted [PRV-15].
    hosts = {name: q.base_url for name, q in QUIRKS.items()}
    assert hosts == {
        "openai": "https://api.openai.com/v1",
        "azure": None,
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama": "http://localhost:11434/v1",
    }


def test_azure_needs_an_endpoint_and_uses_the_deployment_path() -> None:
    env = {"AZURE_OPENAI_API_KEY": "k"}
    with pytest.raises(ConfigError, match="no endpoint configured"):
        resolve("azure/dep", Config(), env=env)
    _, transport, _, _ = run(
        "azure/dep",
        [ok(openai_sse(Reply(text="hi"), "azure"))],
        env=env | {"AZURE_OPENAI_ENDPOINT": "https://r.openai.azure.com"},
    )
    (request,) = transport.requests
    assert request.url == (
        "https://r.openai.azure.com/openai/deployments/dep/chat/completions?api-version=2024-10-21"
    )
    assert request.headers["api-key"] == "k" and "authorization" not in request.headers


def test_keys_come_from_the_environment_and_are_sent_as_bearer() -> None:
    _, transport, _, _ = run("openai/gpt-5", [ok(openai_sse(Reply(text="hi")))])
    assert transport.requests[0].headers["authorization"] == "Bearer k"
    assert transport.requests[0].body["stream_options"] == {"include_usage": True}


# cost [BUD-5]


def test_cost_counts_cache_reads_at_their_own_price() -> None:
    price = PriceSection(input=2.0, output=10.0, cache_read=0.5)
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=400_000)
    assert cost_of("p/m", usage, {"p/m": price}) == pytest.approx(0.6 * 2 + 0.4 * 0.5 + 1.0)


def test_unknown_pricing_is_none_never_zero() -> None:
    assert cost_of("p/unknown", Usage(10, 10), BUILTIN) is None


def test_each_cost_source(tmp_project: Path) -> None:
    openrouter, *_ = run("openrouter/x", [ok(openai_sse(Reply(text="hi", cost=0.5), "openrouter"))])
    assert openrouter.cost == 0.5  # what the provider billed, not our table
    ollama, *_ = run("ollama/qwen3", [ok(openai_sse(Reply(text="hi"), "ollama"))])
    assert ollama.cost == 0.0  # it runs on your machine
    priced, *_ = run("openai/gpt-5", [ok(openai_sse(Reply(text="hi")))])
    assert priced.cost == pytest.approx((21 * 1.25 + 7 * 10.0) / 1_000_000)
    config = Config(pricing={"openai/mine": PriceSection(1.0, 1.0)})
    mine, *_ = run("openai/mine", [ok(openai_sse(Reply(text="hi")))], config=config)
    assert mine.cost == pytest.approx(28 / 1_000_000)


def test_a_server_that_reports_no_usage_is_counted_and_flagged() -> None:  # [PRV-6]
    body = openai_sse(Reply(text="hi there"))
    body = "".join(part + "\n\n" for part in body.split("\n\n") if part and '"usage"' not in part)
    response, *_ = run("ollama/qwen3", [ok(body)])
    assert response.usage.approximate and response.usage.input_tokens > 0


# errors and retries [PRV-7]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("3", 3.0), ("-1", 0.0), ("soon", None), ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0)],
)
def test_retry_after(value: str | None, expected: float | None) -> None:
    assert _retry_after(value) == expected


def test_backoff_is_capped_and_jittered() -> None:
    retry = Retry(base_s=1.0, cap_s=5.0)
    assert all(0 <= retry.delay(n, None) <= 5.0 for n in range(1, 10))
    assert retry.delay(3, 2.5) == 2.5


def test_retries_are_given_up_after_the_last_attempt() -> None:
    busy = error(503, {"error": {"message": "busy"}}, retry_after="0")
    with pytest.raises(ProviderError, match="HTTP 503: busy"):
        run("openai/gpt-5", [busy] * 3, retry=Retry(attempts=3))


def test_a_retry_after_beyond_the_cap_is_an_error_not_a_hang() -> None:
    later = error(429, {"error": {"message": "later"}}, retry_after="3600")
    with pytest.raises(ProviderError, match="429"):
        run("openai/gpt-5", [later])


def test_connection_errors_are_retried() -> None:
    class Flaky(Replay):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if not self.requests:
                self.requests.append(None)  # type: ignore[arg-type]
                raise httpx.ConnectError("refused")
            return await super().handle_async_request(request)

    transport = Flaky([ok(openai_sse(Reply(text="hi")))])
    provider, model = resolve("openai/gpt-5", env=KEYS, transport=transport, retry=Retry(base_s=0))
    recorder, bus = Recorder(), EventBus()
    bus.subscribe(recorder)
    asyncio.run(provider.stream([Message.user("hi")], [], model=model, bus=bus))
    assert [e.reason for e in recorder.of(ProviderRetry)] == ["connection error"]


@pytest.mark.parametrize(
    ("status", "message", "kind", "hint"),
    [
        (400, "This model's maximum context length is 8192 tokens", ContextOverflow, "new session"),
        (400, "prompt is too long: 250000 tokens > 200000 maximum", ContextOverflow, "new session"),
        (
            400,
            "registry.ollama.ai/library/gemma does not support tools",
            ProviderError,
            "native_tools = false",
        ),
        (404, "model not found", ProviderError, "model name"),
    ],
)
def test_errors_are_mapped_with_a_hint(
    status: int, message: str, kind: type[EdgarError], hint: str
) -> None:
    with pytest.raises(kind) as info:
        run("ollama/x", [error(status, {"error": message})])
    assert hint in (info.value.hint or "")


def test_a_stream_that_fails_part_way_raises() -> None:
    failure = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    body = f"event: error\ndata: {json.dumps(failure)}\n\n"
    with pytest.raises(ProviderError, match="overloaded_error"):
        run("anthropic/claude-sonnet-4-5", [ok(body)])


# adapter details the contract does not reach


def test_text_tools_travel_in_the_system_message_when_the_server_has_none() -> None:
    config = Config(providers={"ollama": ProviderSection(native_tools=False)})
    call = ToolUseBlock("c1", "read", {"path": "a"})
    result = ToolResultBlock("c1", (TextBlock("contents"),))
    messages = [
        Message("system", (TextBlock("sys"),)),
        Message.user("read a"),
        Message("assistant", (call,)),
        Message("tool", (result,)),
    ]
    reply = 'Reading it: {"name": "read", "arguments": {"path": "b"}}'
    response, transport, _, _ = run(
        "ollama/m", [ok(openai_sse(Reply(text=reply), "ollama"))], messages, config=config
    )
    body = transport.requests[0].body
    assert "tools" not in body
    assert "## Calling tools" in body["messages"][0]["content"]
    assert body["messages"][2]["content"] == '{"name": "read", "arguments": {"path": "a"}}'
    assert body["messages"][3] == {"role": "user", "content": "Tool result:\ncontents"}
    assert response.message.tool_calls[0].args == {"path": "b"}


def test_malformed_arguments_are_kept_and_sent_back_as_they_came() -> None:
    body = openai_sse(Reply(calls=[("c1", "read", {})]), "ollama")  # arguments in one piece
    body = body.replace('"arguments": "{}"', '"arguments": "{\\"path\\": "')
    response, *_ = run("ollama/m", [ok(body)])
    (call,) = response.message.tool_calls
    assert call.args == {} and call.malformed == '{"path": '


def test_anthropic_marks_two_cache_breakpoints_and_merges_user_turns() -> None:  # [PRV-8]
    call = ToolUseBlock("toolu_1", "read", {"path": "a"})
    messages = [
        Message("system", (TextBlock("sys"),)),
        Message.user("read a"),
        Message("assistant", (call,)),
        Message("tool", (ToolResultBlock("toolu_1", (TextBlock("ok"),), is_error=True),)),
        Message.user("steer", via="steer"),
    ]
    _, transport, _, _ = run(
        "anthropic/claude-sonnet-4-5", [ok(anthropic_sse(Reply(text="k")))], messages
    )
    body = transport.requests[0].body
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    last = body["messages"][-1]
    assert [b["type"] for b in last["content"]] == ["tool_result", "text"]
    assert last["content"][0]["is_error"] is True
    assert last["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert transport.requests[0].headers["anthropic-version"] == "2023-06-01"


def test_anthropic_replays_redacted_thinking_and_counts_cached_input() -> None:
    origin = "anthropic:claude-sonnet-4-5"
    messages = [
        Message.user("hi"),
        Message("assistant", (ThinkingBlock("", origin, redacted="opaque"), TextBlock("hello"))),
        Message.user("again"),
    ]
    sse = anthropic_sse(Reply(text="k")).replace(
        '"cache_read_input_tokens": 0', '"cache_read_input_tokens": 100'
    )
    response, transport, _, _ = run("anthropic/claude-sonnet-4-5", [ok(sse)], messages)
    assert transport.requests[0].body["messages"][1]["content"][0] == {
        "type": "redacted_thinking",
        "data": "opaque",
    }
    assert (response.usage.input_tokens, response.usage.cache_read_tokens) == (121, 100)


def test_anthropic_rejects_keys_meant_for_openai_compatible_servers() -> None:
    config = Config(providers={"anthropic": ProviderSection(native_tools=False)})
    with pytest.raises(ConfigError, match="does not use"):
        resolve("anthropic/x", config, env=KEYS)


def test_token_counts_are_corrected_by_what_the_provider_reports() -> None:  # [OQ-3]
    messages = [Message.user("x" * 400)]  # 100 tokens by the four-character rule
    reply = Reply(text="k", input_tokens=150)
    _, _, _, provider = run("openai/gpt-5", [ok(openai_sse(reply))], messages)
    assert provider.count_tokens(messages) == 150


# routing and profiles [ROUTE-1, PRV-15, PRV-17]


def test_auxiliary_roles_use_the_main_model_unless_named() -> None:
    models = ModelSection(default="a/main", compactor="b/small")
    assert select_model(RoutingContext(role="compactor"), models).model == "b/small"
    chosen = select_model(RoutingContext(role="controller"), models)
    assert (chosen.model, chosen.rule) == ("a/main", "default")
    agent = RoutingContext(role="subagent", agent="explorer", agent_model="ollama/qwen3")
    assert select_model(agent, models).rule == "agent"


def test_no_model_at_all_is_an_error_not_a_default() -> None:
    with pytest.raises(ConfigError, match="no model configured"):
        select_model(RoutingContext(role="compactor"), ModelSection())


@pytest.mark.parametrize(
    ("setting", "window", "expected"),
    [
        ("auto", 8_192, "compact"),
        ("auto", 200_000, "full"),
        ("full", 4_096, "full"),
        ("compact", 1_000_000, "compact"),
    ],
)
def test_profiles(setting: str, window: int, expected: str) -> None:
    assert choose_profile(setting, window) == expected


def test_the_compact_prompt_is_short(tmp_project: Path) -> None:
    full, compact = load_prompt(tmp_project), load_prompt(tmp_project, "compact")
    assert len(compact.text) < len(full.text) / 2


def test_reasoning_origin_names_the_family() -> None:
    assert ThinkingBlock("x", "anthropic:claude").family == "anthropic"
    assert Usage(1, 2) + Usage(3, 4, approximate=True, repairs=1) == Usage(4, 6, 0, 0, True, 1)


def test_an_unreadable_stream_event_is_a_provider_error() -> None:
    with pytest.raises(ProviderError, match="unreadable stream event"):
        run("openai/gpt-5", [ok("data: {not json\n\n")])
