"""A static import graph of ``src/edgar``, built from the AST.

Every import statement counts, including ones inside functions and under
``TYPE_CHECKING``: a lazy import is still a dependency. A module loaded by name
through ``importlib`` is not, which is exactly how v2 attaches (ADR-0015).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Module:
    name: str
    path: Path
    imports: frozenset[str]


def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve(node: ast.ImportFrom, name: str, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    base = name.split(".")
    # A package's own __init__ resolves "." to itself; a plain module to its parent.
    drop = node.level - 1 if is_package else node.level
    anchor = base[: len(base) - drop] if drop else base
    return ".".join([*anchor, node.module] if node.module else anchor)


def imports_of(path: Path, name: str) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_package = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node, name, is_package)
            found.add(base)
            # "from edgar.providers import anthropic" imports a submodule; record it.
            found.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return frozenset(found)


def static_import_graph(root: Path) -> list[Module]:
    modules = []
    for path in sorted(root.rglob("*.py")):
        name = module_name(path, root)
        modules.append(Module(name, path, imports_of(path, name)))
    return modules
