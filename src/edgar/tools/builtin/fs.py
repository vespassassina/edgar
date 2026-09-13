"""File system built-ins: `read` `ls` `glob` `grep` `write` `edit` [TOOL-5].

Paths are relative to the working directory. The permission check has already
resolved each path and decided about it before these run; `glob` and `grep`
also drop anything that resolves outside the working directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from edgar.tools.base import ToolContext, ToolResult, ToolSchema

READ_LIMIT = 2000  # lines
LS_LIMIT = 1000  # entries
GREP_LIMIT = 500  # matching lines
SKIP = {".git", ".edgar", ".venv", "node_modules", "__pycache__"}


def _schema(
    name: str, description: str, props: dict[str, Any], required: list[str], category: str = "read"
) -> ToolSchema:
    return ToolSchema(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": False,
        },
        kind="builtin",
        origin="builtin",
        category=category,  # type: ignore[arg-type]  # one of the Category literals
    )


_PATH = {"type": "string", "description": "relative to the working directory"}


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


def _files(root: Path, pattern: str, cwd: Path) -> list[Path]:
    """Files under `root` matching `pattern`, never outside `cwd`, skipping tool dirs."""
    base = cwd.resolve()
    found = []
    for path in root.glob(pattern):
        resolved = path.resolve()
        if SKIP.intersection(path.relative_to(root).parts) or resolved == base:
            continue
        if resolved.is_relative_to(base):
            found.append(resolved)
    return sorted(found)


class Glob:
    schema = _schema(
        "glob",
        "Find files by pattern, for example '**/*.py'. Paths come back relative to the "
        "working directory.",
        {"pattern": {"type": "string"}, "path": _PATH},
        ["pattern"],
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            paths = _files(ctx.cwd / args.get("path", "."), args["pattern"], ctx.cwd)
        except (ValueError, NotImplementedError) as exc:
            return ToolResult(f"bad pattern: {exc}", error="validation")
        names = [p.relative_to(ctx.cwd.resolve()).as_posix() for p in paths]
        shown = "\n".join(names[:LS_LIMIT]) or "no matches"
        if len(names) > LS_LIMIT:
            shown += f"\n[{len(names) - LS_LIMIT} more not shown; narrow the pattern]"
        return ToolResult(shown)


class Grep:
    schema = _schema(
        "grep",
        "Search file contents with a Python regular expression. Returns path:line:text.",
        {
            "pattern": {"type": "string"},
            "path": _PATH,
            "glob": {"type": "string", "description": "which files, default '**/*'"},
            "ignore_case": {"type": "boolean"},
        },
        ["pattern"],
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            regex = re.compile(args["pattern"], re.IGNORECASE if args.get("ignore_case") else 0)
            paths = _files(ctx.cwd / args.get("path", "."), args.get("glob", "**/*"), ctx.cwd)
        except (re.error, ValueError, NotImplementedError) as exc:
            return ToolResult(f"bad pattern: {exc}", error="validation")
        hits: list[str] = []
        for path in paths:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            data = path.read_bytes()
            if b"\0" in data[:8192]:
                continue
            rel = path.relative_to(ctx.cwd.resolve()).as_posix()
            for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{n}:{line[:300]}")
                    if len(hits) >= GREP_LIMIT:
                        return ToolResult("\n".join(hits) + "\n[more matches not shown]")
        return ToolResult("\n".join(hits) or "no matches")


class Write:
    schema = _schema(
        "write",
        "Create or overwrite a text file. Parent folders are created.",
        {"path": _PATH, "content": {"type": "string"}},
        ["path", "content"],
        "write",
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.cwd / args["path"]
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8", newline="")
        return ToolResult(f"{'overwrote' if existed else 'created'} {args['path']}")


class Edit:
    schema = _schema(
        "edit",
        "Replace exact text in a file. `old` must match the file exactly and only once, "
        "unless replace_all is true. Read the file first.",
        {
            "path": _PATH,
            "old": {"type": "string", "minLength": 1},
            "new": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        ["path", "old", "new"],
        "write",
    )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.cwd / args["path"]
        try:
            with path.open(encoding="utf-8", newline="") as handle:  # keep line endings
                text = handle.read()
        except FileNotFoundError:
            return ToolResult(f"no such file: {args['path']}", error="not_found")
        count = text.count(args["old"])
        if count == 0:
            return ToolResult("`old` was not found; copy it exactly from read", error="validation")
        if count > 1 and not args.get("replace_all"):
            return ToolResult(
                f"`old` appears {count} times; add context or set replace_all", error="validation"
            )
        path.write_text(text.replace(args["old"], args["new"]), encoding="utf-8", newline="")
        return ToolResult(f"edited {args['path']}: {count} replacement{'s' * (count > 1)}")


def builtins(shell: str = "auto") -> tuple[Any, ...]:
    from edgar.tools.builtin.shell import Fetch, Shell

    return (Read(), Ls(), Glob(), Grep(), Write(), Edit(), Shell(shell), Fetch())
