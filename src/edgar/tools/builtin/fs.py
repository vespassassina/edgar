"""File system built-ins. M1 ships `read` and `ls`; `write`, `edit`, `glob` and `grep`
arrive with the full permission engine in M3 [TOOL-5].

Paths are relative to the working directory. The policy has already refused any
path that resolves outside it before these run.
"""

from __future__ import annotations

from typing import Any

from edgar.tools.base import ToolContext, ToolResult, ToolSchema

READ_LIMIT = 2000  # lines
LS_LIMIT = 1000  # entries


class Read:
    schema = ToolSchema(
        name="read",
        description=(
            "Read a text file. Lines are numbered from 1. For long files pass offset "
            f"(first line) and limit (line count, default {READ_LIMIT})."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "relative to the working directory"},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        kind="builtin",
        origin="builtin",
        category="read",
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.cwd / args["path"]
        offset, limit = args.get("offset", 1), args.get("limit", READ_LIMIT)
        # Checked first: Windows reports reading a directory as PermissionError.
        if path.is_dir():
            return ToolResult(f"{args['path']} is a directory; use ls", error="validation")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return ToolResult(f"no such file: {args['path']}", error="not_found")
        except PermissionError:
            return ToolResult(f"the OS denied reading {args['path']}", error="permission_denied")
        if b"\0" in data[:8192]:
            return ToolResult(f"{args['path']} looks binary; not shown", error="validation")
        lines = data.decode("utf-8", errors="replace").splitlines()
        if not lines:
            return ToolResult(f"{args['path']} is empty")
        window = lines[offset - 1 : offset - 1 + limit]
        numbered = "\n".join(f"{n:>6}\t{line}" for n, line in enumerate(window, start=offset))
        remaining = len(lines) - (offset - 1 + len(window))
        if remaining > 0:
            next_offset = offset + len(window)
            numbered += f"\n[{remaining} more lines; continue with offset={next_offset}]"
        return ToolResult(numbered)


class Ls:
    schema = ToolSchema(
        name="ls",
        description="List a directory. Directories end with '/'.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "relative to the working directory"},
            },
            "additionalProperties": False,
        },
        kind="builtin",
        origin="builtin",
        category="read",
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.cwd / args.get("path", ".")
        try:
            entries = sorted(path.iterdir(), key=lambda p: p.name)
        except FileNotFoundError:
            return ToolResult(f"no such directory: {args.get('path', '.')}", error="not_found")
        except NotADirectoryError:
            return ToolResult(f"{args.get('path')} is a file; use read", error="validation")
        except PermissionError:
            return ToolResult("the OS denied listing this directory", error="permission_denied")
        names = [p.name + ("/" if p.is_dir() else "") for p in entries]
        shown = "\n".join(names[:LS_LIMIT]) or "(empty)"
        if len(names) > LS_LIMIT:
            shown += f"\n[{len(names) - LS_LIMIT} more entries not shown]"
        return ToolResult(shown)


BUILTINS = (Read(), Ls())
