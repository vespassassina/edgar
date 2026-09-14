"""Tools by name, which one wins a name, and which schemas a request can afford
[TOOL-9, TOOL-15].

    project custom  >  user custom  >  MCP  >  built-in

Extensions join the order in M10. A replaced tool is reported, never silent.
"""

# Building a registry:
#
#   for each tool, lowest priority first (built-ins, the `skill` tool, MCP, user,
#   project): a tool whose name is taken replaces the old one, and a warning says so
#   if the schemas together cost more than tools.schema_budget, the MCP ones are
#   deferred: named in tool_search's description, and sent in full only once
#   tool_search has loaded them [TOOL-15]
#
# The registry then answers "which tool is called NAME?" and "which schemas go in
# the request?". A deferred tool is still callable by name: deferral saves tokens,
# it does not hide anything.

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from edgar.context.tokens import approx_tokens
from edgar.tools.base import Tool, ToolSchema


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = (), budget: int | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.warnings: list[str] = []
        self.deferred: dict[str, Tool] = {}  # loaded on demand by tool_search
        self.budget = budget
        for tool in tools:
            old = self._tools.get(tool.schema.name)
            if old is not None:
                self.warnings.append(
                    f"the {tool.schema.origin} tool {tool.schema.name!r} replaces the "
                    f"{old.schema.origin} one"
                )
            self._tools[tool.schema.name] = tool

        if budget is not None and cost(self.schemas()) > budget:
            self.deferred = {n: t for n, t in self._tools.items() if _defers(t)}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def exposed(self) -> list[Tool]:
        """The tools whose schemas the next request carries."""
        return [t for n, t in self._tools.items() if n not in self.deferred]

    def schemas(self) -> list[ToolSchema]:
        """What goes in the request: everything but the tools still deferred."""
        return [tool.schema for tool in self.exposed()]

    def names(self) -> list[str]:
        return list(self._tools)

    def add(self, tools: Iterable[Tool], *, defer: bool | None = None) -> None:
        """Tools found after the session started: an MCP server discovered by
        `tool_search`, or the browser `/browser` connected."""
        for tool in tools:
            self._tools[tool.schema.name] = tool
            over = self.budget is not None and cost(self.schemas()) > self.budget
            if defer if defer is not None else (_defers(tool) and over):
                self.deferred[tool.schema.name] = tool

    def load(self, names: Iterable[str]) -> list[ToolSchema]:
        """Expose deferred tools for the rest of the session. They join the list at
        the end, so what the model already saw keeps its place."""
        loaded = []
        for name in names:
            tool = self.deferred.pop(name, None) or self._tools.get(name)
            if tool is not None:
                self._tools[name] = self._tools.pop(name)  # moved to the end
                loaded.append(tool.schema)
        return loaded


def cost(schemas: Iterable[ToolSchema]) -> int:
    """Roughly what these schemas cost in a request [TOOL-15]."""

    def described(s: ToolSchema) -> str:
        return json.dumps(
            {"name": s.name, "description": s.description, "input": s.input_schema},
            ensure_ascii=False,
        )

    return sum(approx_tokens(described(s)) for s in schemas)


def _defers(tool: Tool) -> bool:
    # Built-ins and the tools a human wrote are always sent; MCP is what grows
    # without bound. Extensions join it in M10.
    return tool.schema.kind == "mcp"


def core_registry(shell: str = "auto") -> ToolRegistry:
    from edgar.tools.builtin.fs import builtins

    return ToolRegistry(builtins(shell))


def registry_for(
    cwd: Path,
    home: Path,
    *,
    shell: str,
    project_exec: bool,
    extra: Iterable[Tool] = (),
    mcp: Iterable[Tool] = (),
    budget: int | None = None,
) -> ToolRegistry:
    """Built-ins and `extra` (the `skill` tool), then the MCP servers' tools, then
    `~/.edgar/tools/*.toml`, then, in a trusted project, `.edgar/tools/*.toml`
    [PERM-13]. Later beats earlier, so a tool a human wrote wins its name."""
    from edgar.tools.builtin.fs import builtins
    from edgar.tools.custom import load

    folders = [(home / ".edgar" / "tools", "user")]
    if project_exec:
        folders.append((cwd / ".edgar" / "tools", "project"))
    return ToolRegistry([*builtins(shell), *extra, *mcp, *load(folders)], budget=budget)
