"""MCP servers as tools (M8) [TOOL-7, TOOL-8, TOOL-9, TOOL-13, TOOL-15, PERM-13, CLI-29].

A real stdio server (`tests/support/mcp_server.py`, driven with `sys.executable`)
and a Streamable HTTP one (httpx's MockTransport) exercise the two transports; the
rest is about what a session pays for them and what they are allowed to do.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from harness import new_session, runtime, scripted, tool_use
from scripted import ScriptedResponse

from edgar.cli import trust
from edgar.cli.admin import command
from edgar.cli.setup import toolset
from edgar.config.load import load
from edgar.config.schema import McpSection
from edgar.core.errors import ConfigError
from edgar.core.events import EventBus
from edgar.core.loop import run_turn
from edgar.storage.db import Store
from edgar.tools.base import ToolContext
from edgar.tools.builtin.fs import builtins
from edgar.tools.builtin.tool_search import searchable
from edgar.tools.mcp.client import McpTool, Server, close, servers
from edgar.tools.mcp.schema import hints, to_result, tool_name
from edgar.tools.registry import ToolRegistry, cost

SERVER = Path(__file__).parents[1] / "support" / "mcp_server.py"


def block(**extra: Any) -> McpSection:
    return McpSection(command=sys.executable, args=[str(SERVER)], **extra)


def one(root: Path, home: Path, **extra: Any) -> Server:
    return Server("fake", block(**extra), root, Store(home / ".edgar" / "edgar.db"))


def ask(server: Server, call: Any) -> Any:
    async def run() -> Any:
        try:
            return await call(server)
        finally:
            await server.close()

    return asyncio.run(run())


def test_a_stdio_server_lists_every_page_and_answers_a_call(tmp_project: Path, home: Path) -> None:
    server = one(tmp_project, home)
    tools = ask(server, lambda s: s.discover())
    assert [t.schema.name for t in tools] == [
        "mcp__fake__echo",
        "mcp__fake__fail",
        "mcp__fake__secret",  # the second page [TOOL-7]
    ]
    echo, fail = tools[0], tools[1]
    assert (echo.schema.kind, echo.schema.origin) == ("mcp", "mcp:fake")
    assert echo.schema.category == "shell" and echo.schema.untrusted_output  # [TOOL-13]
    assert hints(echo.raw) == "readOnlyHint"  # shown to a human, never to decide()
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)
    result = ask(one(tmp_project, home), lambda s: McpTool(s, echo.raw).run({"text": "hi"}, ctx))
    assert result.text == "echo: hi\n[image]" and result.error is None
    failed = ask(one(tmp_project, home), lambda s: McpTool(s, fail.raw).run({}, ctx))
    assert failed.error == "nonzero_exit"


def test_the_tool_list_is_remembered_so_the_next_session_starts_nothing(
    tmp_project: Path, home: Path
) -> None:
    assert one(tmp_project, home).tools() is None  # never started: nothing to offer
    ask(one(tmp_project, home), lambda s: s.discover())
    again = one(tmp_project, home)
    cached = again.tools()
    assert cached is not None and len(cached) == 3 and again.transport is None  # [TOOL-8]
    assert one(tmp_project, home, env={"X": "1"}).tools() is None  # a changed block is new


def test_an_env_secret_is_expanded_for_the_server_and_scrubbed_from_its_output(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "hunter2000")
    server = one(tmp_project, home, env={"TOKEN": "${env:SECRET_TOKEN}"})
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)
    result = ask(server, lambda s: McpTool(s, {"name": "secret"}).run({}, ctx))
    assert result.text == "TOKEN=[redacted]"  # the server saw it; the model does not


def test_a_missing_program_and_a_missing_variable_come_back_as_tool_errors(
    tmp_project: Path, home: Path
) -> None:
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)
    gone = Server("gone", McpSection(command="no-such-program-here"), tmp_project, Store(home))
    result = ask(gone, lambda s: McpTool(s, {"name": "x"}).run({}, ctx))
    assert result.error == "not_found"
    unset = one(tmp_project, home, env={"TOKEN": "${env:EDGAR_NOT_SET}"})
    result = ask(unset, lambda s: McpTool(s, {"name": "x"}).run({}, ctx))
    assert result.error == "provider_http" and "EDGAR_NOT_SET" in result.text


def test_a_result_from_a_server_taints_the_session(tmp_project: Path, home: Path) -> None:
    server = one(tmp_project, home)
    tools = ask(server, lambda s: s.discover())
    registry = ToolRegistry(tools)
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("mcp__fake__echo", {"text": "hi"})]),
        ScriptedResponse(text="done"),
    )
    session = new_session(tmp_project, mode="yolo")
    rt = runtime(provider, tools=registry)

    async def turn() -> Any:
        # The turn starts the server, so the turn stops it: a pipe belongs to the
        # loop that opened it.
        try:
            return await run_turn(session, "use it", rt)
        finally:
            await close([server])

    result = asyncio.run(turn())
    assert result.text == "done" and session.tainted  # [TOOL-13, PERM-11]
    blocks = [b for m in session.transcript for b in m.content if hasattr(b, "untrusted")]
    assert all(b.untrusted for b in blocks)


def many(count: int) -> list[dict[str, Any]]:
    # Tools the size real servers ship: a paragraph of description and a few
    # arguments, so forty of them are worth deferring [TOOL-15].
    said = "Does thing {n}, at some length, the way a server describes its own tools "
    return [
        {
            "name": f"tool_{n}",
            "description": (said * 2).format(n=n) + ("about the weather." if n == 7 else "."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "where": {"type": "string", "description": "where to do it"},
                    "when": {"type": "string", "description": "when to do it"},
                    "how": {"type": "integer", "description": "how many times"},
                },
                "required": ["where"],
            },
        }
        for n in range(count)
    ]


def loaded(tmp_project: Path, home: Path, count: int = 40) -> tuple[ToolRegistry, Server]:
    server = one(tmp_project, home)
    server.cache.remember(server.digest, many(count))
    tools = server.tools() or []
    registry = ToolRegistry([*builtins("auto"), *tools], budget=4000)
    searchable(registry, [])
    return registry, server


def test_forty_mcp_tools_cost_no_more_than_the_schema_budget(tmp_project: Path, home: Path) -> None:
    registry, _ = loaded(tmp_project, home)
    assert len(registry.deferred) == 40  # [TOOL-15]
    assert cost(registry.schemas()) <= 4000
    exposed = [s.name for s in registry.schemas()]
    assert "read" in exposed and "tool_search" in exposed  # built-ins are never deferred
    assert not any(name.startswith("mcp__") for name in exposed)
    assert registry.get("mcp__fake__tool_7") is not None  # deferred, not hidden


def test_tool_search_loads_the_schemas_it_matches_and_they_go_last(
    tmp_project: Path, home: Path
) -> None:
    registry, _ = loaded(tmp_project, home)
    search = registry.get("tool_search")
    assert search is not None and "mcp__fake__tool_7" in search.schema.description
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)
    result = asyncio.run(search.run({"query": "weather"}, ctx))
    assert "mcp__fake__tool_7" in result.text and "where" in result.text
    assert registry.schemas()[-1].name == "mcp__fake__tool_7"  # joins the list at the end
    assert "mcp__fake__tool_7" not in registry.deferred
    nothing = asyncio.run(search.run({"query": "xyzzy"}, ctx))
    assert "no tool matches" in nothing.text


def test_tool_search_starts_a_server_no_session_has_run_yet(tmp_project: Path, home: Path) -> None:
    server = one(tmp_project, home)
    registry = ToolRegistry(builtins("auto"), budget=4000)
    searchable(registry, [server])
    search = registry.get("tool_search")
    assert search is not None
    assert "not started yet, whose tools a search finds: fake" in search.schema.description
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)

    async def searched() -> Any:
        try:
            return await search.run({"query": "echo"}, ctx)
        finally:
            await close([server])

    result = asyncio.run(searched())
    assert "mcp__fake__echo" in result.text
    assert one(tmp_project, home).tools() is not None  # and it was remembered [TOOL-8]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_session_starts_no_server_and_a_project_server_needs_trust(
    tmp_project: Path, home: Path
) -> None:
    mark = tmp_project / "started.txt"
    _write(
        home / ".edgar" / "config.toml",
        f'[mcp.one]\ncommand = "{sys.executable}"\nargs = ["{SERVER.as_posix()}"]\n'
        f'env = {{ EDGAR_TEST_MARK = "{mark.as_posix()}" }}\n',
    )
    _write(tmp_project / ".edgar" / "config.toml", '[mcp.two]\nurl = "https://example.test/mcp"\n')
    config = load(tmp_project, home=home, env={})
    assert "mcp server two" in trust.executable(tmp_project, config)  # [PERM-13]
    tools, _, found = toolset(tmp_project, home, config, project_exec=False)
    assert [s.name for s in found] == ["one"]  # the untrusted project server is left out
    assert not mark.exists()  # nothing was started [TOOL-8]
    assert tools.get("tool_search") is not None  # both servers are waiting to be asked
    tools, _, found = toolset(tmp_project, home, config, project_exec=True)
    assert [s.name for s in found] == ["one", "two"]


def test_edgar_mcp_list_starts_each_server_and_prints_what_it_offers(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["mcp", "list"], tmp_project, home) == 0
    assert "no MCP servers" in capsys.readouterr().out
    _write(
        home / ".edgar" / "config.toml",
        f'[mcp.fake]\ncommand = "{sys.executable}"\nargs = ["{SERVER.as_posix()}"]\n'
        '[mcp.broken]\ncommand = "no-such-program-here"\n',
    )
    assert command(["mcp", "list"], tmp_project, home) == 1  # one server failed
    shown = capsys.readouterr()
    assert "fake  stdio" in shown.out and "3 tools" in shown.out
    assert "mcp__fake__echo" in shown.out and "readOnlyHint" in shown.out
    assert "broken" in shown.err and "failed" in shown.err
    assert command(["mcp", "test", "fake"], tmp_project, home) == 0


def test_a_block_with_neither_command_nor_url_is_refused(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="either command or url"):
        servers({"bad": McpSection()}, tmp_project, home)


def handler(seen: list[httpx.Request]) -> Any:
    # A Streamable HTTP server: JSON for the handshake, SSE for everything after it.
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        message = json.loads(request.content)
        if message.get("method") == "initialize":
            body = {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "x"}}
            return httpx.Response(200, json=body, headers={"Mcp-Session-Id": "s-1"})
        if "id" not in message:
            return httpx.Response(202)
        if message["method"] == "tools/list":
            result: Any = {"tools": [{"name": "fetch", "description": "Gets a page."}]}
        else:
            result = {"content": [{"type": "text", "text": "a page"}]}
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/message"})
        answer = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result})
        stream = f"event: message\ndata: {note}\n\ndata: {answer}\n\n"
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    return respond


def test_a_streamable_http_server_answers_over_json_and_sse(
    tmp_project: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    transport = httpx.MockTransport(handler(seen))
    made = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return made(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    block = McpSection(url="https://example.test/mcp", headers={"X-Key": "k"})
    server = Server("remote", block, tmp_project, Store(home / ".edgar" / "edgar.db"))
    tools = ask(server, lambda s: s.discover())
    assert [t.schema.name for t in tools] == ["mcp__remote__fetch"]
    assert tools[0].schema.category == "network"  # a remote server is the network
    ctx = ToolContext(tmp_project, EventBus(), tmp_project, 8000)
    server = Server("remote", block, tmp_project, Store(home / ".edgar" / "edgar.db"))
    result = ask(server, lambda s: McpTool(s, tools[0].raw).run({"url": "x"}, ctx))
    assert result.text == "a page"
    later = seen[-1].headers
    assert later["mcp-session-id"] == "s-1" and later["x-key"] == "k"
    assert later["mcp-protocol-version"] == "x"  # the version the server agreed to


def test_names_are_what_every_provider_accepts_and_results_carry_what_they_can() -> None:
    assert tool_name("my server", "do/it") == "mcp__my_server__do_it"  # [TOOL-9]
    assert len(tool_name("s" * 60, "t" * 60)) == 64
    held = {"content": [{"type": "resource", "resource": {"uri": "file:///a", "text": "in it"}}]}
    assert to_result(held).text == "in it"
    assert to_result({"structuredContent": {"a": 1}}).text == '{"a": 1}'
