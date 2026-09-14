"""`tool_search`: the schemas a request could not afford, on demand [TOOL-15].

Forty MCP tools can cost more than the conversation they serve, and a turn calls
one or two of them. So when the schemas together pass `tools.schema_budget`, the
MCP ones are deferred: this tool's description lists them by name and a line, and
a search loads the full schemas of the matches for the rest of the session.
"""

# schema   built fresh each request: the names still waiting, as many as the
#          budget leaves room for, and the servers not started yet
# run      1. start the servers never started, so their tools can be found
#          2. score every deferred tool by how many of the query's words it holds
#          3. load the best few, and return their schemas
#
# Nothing here hides a tool: a deferred tool called by name still runs. This is a
# way of spending the schema budget, not a permission boundary.

from __future__ import annotations

import json
from typing import Any

from edgar.context.tokens import approx_tokens
from edgar.tools.base import ToolContext, ToolResult, ToolSchema
from edgar.tools.mcp.client import FAILURES, Server
from edgar.tools.registry import ToolRegistry, cost

FOUND = 5  # schemas per search: enough to choose between, cheap enough to send
RESERVE = 200  # tokens kept back from the budget for this tool's own schema


class ToolSearch:
    """Reads nothing and writes nothing: it only decides what is in the request."""

    def __init__(self, registry: ToolRegistry, waiting: list[Server]) -> None:
        self.registry, self.waiting = registry, waiting

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="tool_search",
            description=self._description(),
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "what you need to do"}},
                "required": ["query"],
            },
            kind="builtin",
            origin="builtin",
            category="read",
            read_only=True,
        )

    def _description(self) -> str:
        # The listing is what a deferred tool costs until it is loaded: one line
        # each, and only as many as fit in what the budget has left.
        # Every exposed schema but this one: asking for its own would not end.
        others = [t.schema for t in self.registry.exposed() if t is not self]
        room = (self.registry.budget or 0) - cost(others) - RESERVE
        lines: list[str] = []
        left = max(room, 0)
        for name, tool in self.registry.deferred.items():
            said = tool.schema.description.strip().splitlines()
            line = f"  {name}: {said[0][:80] if said else ''}"
            left -= approx_tokens(line)
            if left < 0:
                lines.append(f"  … and {len(self.registry.deferred) - len(lines)} more")
                break
            lines.append(line)
        parts = ["Loads the full schema of a tool listed here, so you can then call it."]
        if lines:
            parts += ["Tools waiting, by name and what they do:", *lines]
        if self.waiting:
            named = ", ".join(s.name for s in self.waiting)
            parts.append(f"Servers not started yet, whose tools a search finds: {named}.")
        return "\n".join(parts)

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        notes = await self._start()
        words = [w for w in str(args.get("query", "")).lower().split() if len(w) > 1]
        scored: list[tuple[int, str]] = []
        for name, tool in self.registry.deferred.items():
            text = f"{name} {tool.schema.description}".lower()
            scored.append((sum(word in text for word in words), name))
        best = [name for score, name in sorted(scored, reverse=True) if score][:FOUND]
        loaded = self.registry.load(best)
        if not loaded:
            known = ", ".join(self.registry.deferred) or "none"
            return ToolResult("\n".join([*notes, f"no tool matches. Waiting: {known}"]))
        shown = [
            {"name": s.name, "description": s.description, "input": s.input_schema} for s in loaded
        ]
        return ToolResult("\n".join([*notes, json.dumps(shown, ensure_ascii=False, indent=1)]))

    async def _start(self) -> list[str]:
        # A server no session has run yet: start it, list what it offers, and keep
        # the list, so the next session knows it without starting anything [TOOL-8].
        notes: list[str] = []
        for server in list(self.waiting):
            self.waiting.remove(server)
            try:
                self.registry.add(await server.discover(), defer=True)
            except FAILURES as exc:
                notes.append(f"the {server.name} server did not start: {exc}")
        return notes


def searchable(registry: ToolRegistry, waiting: list[Server]) -> None:
    """Give the session a `tool_search` if anything is waiting to be loaded."""
    if (registry.deferred or waiting) and registry.get("tool_search") is None:
        registry.add([ToolSearch(registry, waiting)], defer=False)
