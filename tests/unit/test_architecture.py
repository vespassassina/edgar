"""Layering rules held by tests rather than by review [NFR-12, EXT-11]."""

from __future__ import annotations

from pathlib import Path

import pytest
from importgraph import Module, static_import_graph

SRC = Path(__file__).resolve().parents[2] / "src" / "edgar"

V2 = (
    "edgar.controller",
    "edgar.learning",
    "edgar.schedule",
    "edgar.broker",
    "edgar.providers.escalation",
)

CORE = ("edgar.core", "edgar.context", "edgar.permissions", "edgar.tools.execute")
ADAPTERS = (
    "edgar.providers.openai_compat",
    "edgar.providers.anthropic",
    "edgar.tools.mcp",
    "edgar.sandbox.none",
    "edgar.sandbox.bwrap",
    "edgar.sandbox.seatbelt",
    "edgar.sandbox.container",
    "edgar.memory.recall",
)


def _hits(prefixes: tuple[str, ...], names: frozenset[str]) -> list[str]:
    return sorted(n for n in names if n.startswith(prefixes))


def tier_violations(graph: list[Module]) -> list[str]:
    return [
        f"{m.name} imports {dep}"
        for m in graph
        if not m.name.startswith(V2)
        for dep in _hits(V2, m.imports)
    ]


def adapter_violations(graph: list[Module]) -> list[str]:
    return [
        f"{m.name} imports {dep}"
        for m in graph
        if m.name.startswith(CORE)
        for dep in _hits(ADAPTERS, m.imports)
    ]


def test_core_and_v1_never_import_v2() -> None:
    assert tier_violations(static_import_graph(SRC)) == []


def test_core_imports_no_adapter() -> None:
    assert adapter_violations(static_import_graph(SRC)) == []


# The two rules above pass trivially while src/ is small. These make sure they
# would fail if a violation were planted, so a green run means something.


def _tree(root: Path, files: dict[str, str]) -> Path:
    pkg = root / "edgar"
    for rel, body in files.items():
        path = pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return pkg


@pytest.mark.parametrize(
    "body",
    [
        "import edgar.learning.learner\n",
        "from edgar.controller import triggers\n",
        "from ..schedule import due\n",
        "def later():\n    from ..providers import escalation\n",
    ],
)
def test_planted_v2_import_is_caught(tmp_path: Path, body: str) -> None:
    pkg = _tree(tmp_path, {"__init__.py": "", "core/__init__.py": "", "core/loop.py": body})
    assert tier_violations(static_import_graph(pkg)) != []


def test_v2_may_import_core(tmp_path: Path) -> None:
    pkg = _tree(tmp_path, {"learning/__init__.py": "from ..core import message\n"})
    assert tier_violations(static_import_graph(pkg)) == []


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("core/loop.py", "from edgar.providers import anthropic\n"),
        ("context/builder.py", "from ..memory.recall import Fts5Retriever\n"),
        ("tools/execute.py", "from .mcp.client import McpClient\n"),
        ("permissions/__init__.py", "from ..sandbox import bwrap\n"),
    ],
)
def test_planted_adapter_import_is_caught(tmp_path: Path, rel: str, body: str) -> None:
    pkg = _tree(tmp_path, {rel: body})
    assert adapter_violations(static_import_graph(pkg)) != []


def test_core_may_import_ports(tmp_path: Path) -> None:
    pkg = _tree(
        tmp_path,
        {"core/loop.py": "from ..providers.base import Provider\nfrom ..sandbox import base\n"},
    )
    assert adapter_violations(static_import_graph(pkg)) == []
