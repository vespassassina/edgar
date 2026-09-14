"""The stdio transport: the server is a child process speaking JSON-RPC, a message
to the line [TOOL-7]."""

# open     start the program `[mcp.NAME]` names, in the project, with its own env
# request  write one JSON line to its stdin, then read its stdout until the answer
#          arrives; a notification is skipped and a question from the server is
#          answered, so neither can be mistaken for the answer
# close    close its stdin, which is how MCP asks a local server to stop, and kill
#          it if it stays
# abandon  the loop it was started in is gone, so nothing can be awaited on it:
#          kill the child and let go

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

LIMIT = 16 * 1024 * 1024  # one line may hold a whole file the server read


class Stdio:
    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path) -> None:
        self.argv, self.env, self.cwd = argv, env, cwd
        self.proc: asyncio.subprocess.Process | None = None

    async def open(self) -> None:
        # `npx` is `npx.cmd` on Windows, which create_subprocess_exec finds only by
        # its full path (NFR-6).
        program = shutil.which(self.argv[0]) or self.argv[0]
        self.proc = await asyncio.create_subprocess_exec(
            program,
            *self.argv[1:],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # a server's logging is its own business
            cwd=self.cwd,
            env={**os.environ, **self.env},
            limit=LIMIT,
        )

    async def request(self, message: dict[str, Any]) -> dict[str, Any] | None:
        await self._write(message)
        if "id" not in message:
            return None  # a notification: there is nothing to wait for
        while True:
            line = await self._readline()
            try:
                reply = json.loads(line)
            except ValueError:
                continue  # a server that prints to stdout is noisy, not fatal
            if reply.get("id") == message["id"] and "method" not in reply:
                return dict(reply)
            if "method" in reply and "id" in reply:  # the server asks; only ping is answered
                answer: dict[str, Any] = {"jsonrpc": "2.0", "id": reply["id"]}
                ping = reply["method"] == "ping"
                answer |= {"result": {}} if ping else {"error": {"code": -32601, "message": "no"}}
                await self._write(answer)

    async def close(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None or proc.returncode is not None:
            return
        if proc.stdin is not None:
            with contextlib.suppress(OSError):
                proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 2)
        except TimeoutError:
            with contextlib.suppress(OSError):
                proc.kill()
            await proc.wait()

    def abandon(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(Exception):
                proc.kill()

    async def _write(self, message: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise ConnectionError("the server is not running")
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        await self.proc.stdin.drain()

    async def _readline(self) -> bytes:
        if self.proc is None or self.proc.stdout is None:
            raise ConnectionError("the server is not running")
        line = await self.proc.stdout.readline()
        if not line:
            raise ConnectionError(f"{self.argv[0]} stopped without answering")
        return line
