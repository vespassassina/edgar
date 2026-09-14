"""MCP servers for a session: started on first use, their tool lists remembered
[TOOL-7, TOOL-8, TOOL-13].

Starting five servers to ask each what it can do would cost more than the turn
that follows, and most turns call none of them. So a session starts none: a
server's tools come from a cache in `~/.edgar/edgar.db`, keyed by a hash of its
config block, and the server itself starts the first time one of its tools is
called.
"""

# Server.tools()     what it listed last time, straight from the cache: no process
# Server.discover()  start it, read every page of tools/list, write the cache
# Server.call()      start it if it is not running, then tools/call
# close(servers)     stop the ones that started, when the session or command ends
#
# A server with nothing cached (new, or its block changed) has no tools to offer
# yet: `tool_search` names it and starts it when the model looks for something
# [TOOL-15], and `edgar mcp list` starts every one of them.

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from edgar import __version__
from edgar.config.schema import McpSection
from edgar.core.errors import ConfigError
from edgar.permissions.matcher import Subject
from edgar.storage.db import Store
from edgar.tools.base import ToolContext, ToolResult
from edgar.tools.custom import expand, scrub
from edgar.tools.mcp.http import Http
from edgar.tools.mcp.schema import to_result, to_schema
from edgar.tools.mcp.stdio import Stdio

PROTOCOL = "2025-06-18"


class McpError(Exception):
    """The server answered, and its answer was an error."""


# Everything a server can fail with, in one tuple: a call turns it into a tool
# result the model reads, and a command into a line the human reads.
FAILURES = (OSError, ValueError, KeyError, McpError)


@dataclass
class Server:
    name: str
    block: McpSection
    cwd: Path
    cache: Store
    transport: Stdio | Http | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    loop: Any = None  # the event loop the transport belongs to
    sent: int = 0

    @property
    def local(self) -> bool:
        return self.block.command is not None

    @property
    def where(self) -> str:
        return self.block.command or self.block.url or ""

    @property
    def digest(self) -> str:
        wanted = json.dumps([self.name, asdict(self.block)], sort_keys=True)
        return hashlib.sha256(wanted.encode()).hexdigest()

    def tools(self) -> list[McpTool] | None:
        """The tools it listed last time, or None if it has never been started."""
        listed = self.cache.listed(self.digest)
        return None if listed is None else [McpTool(self, raw) for raw in listed]

    async def discover(self) -> list[McpTool]:
        """Start it and read every page of its tool list, then remember the list."""
        raw: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = await self.request("tools/list", {"cursor": cursor} if cursor else {})
            raw += [t for t in page.get("tools", []) if isinstance(t, dict)]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        self.cache.remember(self.digest, raw)
        return [McpTool(self, one) for one in raw]

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """One request, in its turn: a server answers one message at a time."""
        # A run (a turn, or `edgar mcp list`) has its own event loop, and a pipe
        # from an earlier one cannot be read in this one: start again instead.
        running = asyncio.get_running_loop()
        if self.loop is not running:
            if self.transport is not None:
                self.transport.abandon()
            self.loop, self.transport, self.lock = running, None, asyncio.Lock()
        async with self.lock:
            if self.transport is None:
                await self._open()
            return await self._send(method, params)

    async def close(self) -> None:
        if self.transport is None:
            return
        transport, self.transport = self.transport, None
        if self.loop is not asyncio.get_running_loop():
            transport.abandon()  # nothing can be awaited on a loop that has ended
        else:
            await transport.close()

    async def _open(self) -> None:
        # 1. The transport, with ${env:NAME} read from the environment now, never
        #    stored, and scrubbed from whatever the server sends back.
        b = self.block
        if b.command is not None:
            argv = [b.command, *b.args]
            self.transport = Stdio(argv, {k: expand(v) for k, v in b.env.items()}, self.cwd)
        else:
            headers = {k: expand(v) for k, v in b.headers.items()}
            self.transport = Http(expand(b.url or ""), headers, b.timeout_s)
        await self.transport.open()
        # 2. The handshake: initialize, then say so.
        client = {"name": "edgar", "version": __version__}
        hello = {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": client}
        await self._send("initialize", hello)
        await self.transport.request({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.transport is None:
            raise ConnectionError("the server is not running")
        self.sent += 1
        message = {"jsonrpc": "2.0", "id": self.sent, "method": method, "params": params}
        reply = await self.transport.request(message) or {}
        if "error" in reply:
            said = reply["error"]
            raise McpError(str(said.get("message", said)) if isinstance(said, dict) else str(said))
        result = reply.get("result")
        return result if isinstance(result, dict) else {}


class McpTool:
    """One tool of one server, called through it [TOOL-9]."""

    def __init__(self, server: Server, raw: dict[str, Any]) -> None:
        self.server, self.raw = server, raw
        self.schema = to_schema(server.name, raw, local=server.local)
        self.timeout_s = server.block.timeout_s

    def subject(self, args: dict[str, Any], cwd: Path) -> Subject:
        # Named by what is called and with what, as a shell call is by its command
        # line: the server decides what its arguments mean, so edgar reads no path
        # out of them.
        shown = json.dumps(args, ensure_ascii=False, sort_keys=True)[:120]
        return Subject(f"{self.schema.name} {shown}")

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        called = {"name": str(self.raw.get("name", "")), "arguments": args}
        try:
            payload = await self.server.request("tools/call", called)
        except FileNotFoundError:
            return ToolResult(f"{self.server.where} is not installed or not on PATH", "not_found")
        except FAILURES as exc:
            return ToolResult(scrub(f"MCP server {self.server.name}: {exc}"), "provider_http")
        result = to_result(payload)
        return ToolResult(scrub(result.text), result.error)


def servers(blocks: dict[str, McpSection], cwd: Path, home: Path) -> list[Server]:
    """A Server for each `[mcp.NAME]` block. Nothing is started here [TOOL-8]."""
    cache = Store(home / ".edgar" / "edgar.db")
    found = []
    for name, block in blocks.items():
        if (block.command is None) == (block.url is None):
            raise ConfigError(
                f"[mcp.{name}] needs either command or url, not both and not neither",
                hint='command = "npx" starts a local server, url = "https://…" a remote one',
            )
        found.append(Server(name, block, cwd, cache))
    return found


async def close(found: list[Server]) -> None:
    for server in found:
        await server.close()
