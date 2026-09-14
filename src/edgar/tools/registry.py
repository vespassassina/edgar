"""Tools by name, and which one wins a name [TOOL-9].

    project custom  >  user custom  >  built-in

MCP and extensions join the order in v1. A replaced tool is reported, never
silent.
"""

# Building a registry:
#
#   for each tool, lowest priority first (built-ins, the `skill` tool, user, project):
#     a tool whose name is taken replaces the old one, and a warning says so
#   the registry then answers "which tool is called NAME?" and "which schemas go
#   in the request?"

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from edgar.tools.base import Tool, ToolSchema


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        self.warnings: list[str] = []
        for tool in tools:
            old = self._tools.get(tool.schema.name)
            if old is not None:
                self.warnings.append(
                    f"the {tool.schema.origin} tool {tool.schema.name!r} replaces the "
                    f"{old.schema.origin} one"
                )
            self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[ToolSchema]:
        return [tool.schema for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)


def core_registry(shell: str = "auto") -> ToolRegistry:
    from edgar.tools.builtin.fs import builtins

    return ToolRegistry(builtins(shell))


def registry_for(
    cwd: Path, home: Path, *, shell: str, project_exec: bool, extra: Iterable[Tool] = ()
) -> ToolRegistry:
    """Built-ins and `extra` (the `skill` tool), then `~/.edgar/tools/*.toml`, then,
    in a trusted project, `.edgar/tools/*.toml` [PERM-13]."""
    from edgar.tools.builtin.fs import builtins
    from edgar.tools.custom import load

    folders = [(home / ".edgar" / "tools", "user")]
    if project_exec:
        folders.append((cwd / ".edgar" / "tools", "project"))
    return ToolRegistry([*builtins(shell), *extra, *load(folders)])
