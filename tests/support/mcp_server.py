"""A small MCP server over stdio, for the tests to drive with `sys.executable`.

It answers `initialize`, two pages of `tools/list` and `tools/call`, which is all
of the protocol edgar uses. `EDGAR_TEST_MARK` names a file it creates when it
starts, so a test can prove a session started no server at all [TOOL-8].
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PAGES: dict[str, list[dict[str, Any]]] = {
    "": [
        {
            "name": "echo",
            "description": "Says back what you send it.",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        },
        {"name": "fail", "description": "Always reports an error.", "inputSchema": {}},
    ],
    "two": [{"name": "secret", "description": "Reads TOKEN from its environment."}],
}


def answer(message: dict[str, Any]) -> dict[str, Any] | None:
    method, params = message.get("method"), message.get("params") or {}
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: Any = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "fake"}}
    elif method == "tools/list":
        cursor = params.get("cursor", "")
        result = {"tools": PAGES[cursor]}
        if not cursor:
            result["nextCursor"] = "two"
    elif method == "tools/call":
        result = called(params.get("name", ""), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": method}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def called(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "fail":
        return {"content": [{"type": "text", "text": "no"}], "isError": True}
    if name == "secret":
        return {"content": [{"type": "text", "text": f"TOKEN={os.environ.get('TOKEN', '')}"}]}
    said = str(args.get("text", ""))
    return {"content": [{"type": "text", "text": f"echo: {said}"}, {"type": "image"}]}


def main() -> None:
    mark = os.environ.get("EDGAR_TEST_MARK")
    if mark:
        Path(mark).write_text("started\n", encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        reply = answer(json.loads(line))
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
