"""Tools by name. Sources and collision order arrive with custom tools in M6 [TOOL-9]."""

from __future__ import annotations

from collections.abc import Iterable

from edgar.tools.base import Tool, ToolSchema


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self._tools[tool.schema.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[ToolSchema]:
        return [tool.schema for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)


def core_registry() -> ToolRegistry:
    from edgar.tools.builtin.fs import BUILTINS

    return ToolRegistry(BUILTINS)
