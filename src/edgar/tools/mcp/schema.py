"""MCP and edgar, translated both ways [TOOL-9, TOOL-13].

A server's tool becomes a `ToolSchema` the model can call, and the result of a
call becomes the text a `ToolResult` carries. Nothing else in edgar knows that
MCP exists.
"""

# The tool `search` on the server `docs` is `mcp__docs__search` to the model: the
# prefix says where it came from, and the name keeps to what every provider
# accepts ([A-Za-z0-9_-], 64 characters at most).
#
# What a server says about its own tools (annotations such as readOnlyHint) is
# shown to the human by `edgar mcp list` and never read by decide(): a server
# cannot talk its way into being allowed [TOOL-13].

from __future__ import annotations

import json
import re
from typing import Any

from edgar.tools.base import ToolResult, ToolSchema

_BAD = re.compile(r"[^A-Za-z0-9_-]")


def tool_name(server: str, tool: str) -> str:
    return _BAD.sub("_", f"mcp__{server}__{tool}")[:64]


def to_schema(server: str, raw: dict[str, Any], *, local: bool) -> ToolSchema:
    """One entry of a server's `tools/list` as a tool of this session."""
    params = raw.get("inputSchema")
    return ToolSchema(
        name=tool_name(server, str(raw.get("name", ""))),
        description=str(raw.get("description") or raw.get("title") or raw.get("name", "")),
        input_schema=params if isinstance(params, dict) else {"type": "object", "properties": {}},
        kind="mcp",
        origin=f"mcp:{server}",
        # A local server is a program running with your rights; a remote one is the
        # network. Either way its output is untrusted [TOOL-13].
        category="shell" if local else "network",
        untrusted_output=True,
    )


def to_result(payload: dict[str, Any]) -> ToolResult:
    """The `content` of a `tools/call` result as text; what is not text is named."""
    parts = []
    for item in payload.get("content") or []:
        kind = str(item.get("type", ""))
        if kind == "text":
            parts.append(str(item.get("text", "")))
        elif kind == "resource":
            held = item.get("resource") or {}
            parts.append(str(held.get("text") or f"[resource {held.get('uri', '')}]"))
        else:
            named = item.get("uri") or item.get("mimeType") or ""
            parts.append(f"[{kind} {named}]".replace(" ]", "]"))
    if not parts and "structuredContent" in payload:
        parts.append(json.dumps(payload["structuredContent"], ensure_ascii=False))
    # isError is the server reporting a failed call, not a broken connection.
    return ToolResult("\n".join(parts), "nonzero_exit" if payload.get("isError") else None)


def hints(raw: dict[str, Any]) -> str:
    """What the server claims about a tool, for a human to read and judge."""
    said = raw.get("annotations")
    if not isinstance(said, dict):
        return ""
    return ", ".join(sorted(k for k, v in said.items() if v is True))
