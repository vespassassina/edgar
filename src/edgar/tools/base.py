"""The tool contract, MCP-shaped so MCP is a translation layer, not a second system [TOOL-1]."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from edgar.core.events import EventBus
from edgar.core.message import ErrorKind

Category = Literal["read", "write", "shell", "network", "memory", "agent"]

DEFAULT_TIMEOUT_S = 120.0  # [TOOL-3]


@dataclass(frozen=True, slots=True)
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema
    kind: Literal["builtin", "command", "http", "mcp"]
    origin: str  # "builtin" | "project" | "user" | "ext:<name>" | "mcp:<server>"
    category: Category
    read_only: bool = False  # human assertion for command/http tools [TOOL-6]
    untrusted_output: bool = False  # fetch, http, mcp [TOOL-13]
    dangerous: bool = False  # default to ask even in auto mode


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What a tool returns. The pipeline turns it into a ToolResultBlock."""

    text: str
    error: ErrorKind | None = None  # set when the tool itself reports failure


@dataclass(frozen=True, slots=True)
class ToolContext:
    cwd: Path
    bus: EventBus
    blob_dir: Path  # where spilled output goes [CTX-13]
    max_output_tokens: int
    timeout_s: float = DEFAULT_TIMEOUT_S


class Tool(Protocol):
    @property
    def schema(self) -> ToolSchema: ...

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...
