"""The permission decision: one pure function [PERM-1..5].

This is the M1 subset. It allows what the read tools need and nothing else: reads
inside the working directory, in any mode. Everything outside that is denied until
the full policy lands in M3, with rules, grants, taint, control files and hostile
path matching (§7). Denying by default keeps M1 safe to run anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar.tools.base import ToolSchema

MODES = ("read-only", "ask", "auto", "yolo")  # [PERM-1]


@dataclass(frozen=True, slots=True)
class Allow:
    source: str = "mode"


@dataclass(frozen=True, slots=True)
class Deny:
    reason: str
    source: str = "mode"


Decision = Allow | Deny


def decide(tool: ToolSchema, args: dict[str, Any], *, mode: str, cwd: Path) -> Decision:
    if tool.category != "read":
        return Deny(f"{tool.category} tools are not available yet (milestone M3)")
    path = args.get("path")
    if isinstance(path, str) and not _inside(cwd, path):
        return Deny(f"{path} is outside the working directory {cwd}")
    return Allow()


def _inside(root: Path, path: str) -> bool:
    # resolve() follows symlinks and collapses "..", so a link or a traversal that
    # leaves the root is judged by where it lands, not by how it is spelled.
    root = root.resolve()
    return (root / path).resolve().is_relative_to(root)
