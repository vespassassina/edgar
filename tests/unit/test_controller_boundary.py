"""Two things the controller can never do, held statically [CTRL-12, ADR-0017, ADR-0007].

The controller is the one component that acts on the harness itself, so the two
limits that matter most are the ones a reviewer cannot keep checking by eye:

1. it never writes a memory fact — there is no `learn` action, and this test says
   the code to write one is not even reachable from the package;
2. it never writes `AGENTS.md` or `config.toml`, in any mode, dry-run or not.

Both are architecture-style tests rather than greps over the repository, because a
grep cannot tell a comment from a path and would have to be loosened the first time
someone writes the file name in prose. The first walks the same static import graph
`test_architecture.py` uses, closed over `edgar.*` so an indirect route counts. The
second reads every string literal in the package: a file edgar does not name is a
file edgar cannot open.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from importgraph import static_import_graph

SRC = Path(__file__).resolve().parents[2] / "src" / "edgar"
PACKAGE = SRC / "controller"

# memory/store.py is the only writer of facts; recall.py and markdown.py read and
# render them. Those three are out of bounds. The rest of edgar.memory is not:
# redact.py is a pure secret scrubber that storage/transcript.py uses, so it is
# reachable from almost everything and says nothing about facts.
FORBIDDEN = ("edgar.memory.store", "edgar.memory.recall", "edgar.memory.markdown")

# The hand-authored files, by every spelling that could reach the filesystem.
HAND_AUTHORED = ("AGENTS.md", "CLAUDE.md", "config.toml")


def _reachable(start: str) -> frozenset[str]:
    # An iterative closure rather than a recursive walk: the graph has cycles and
    # the rule is about what the package can reach at all, however far away.
    graph = {m.name: m.imports for m in static_import_graph(SRC)}
    seen: set[str] = set()
    queue = [name for name in graph if name == start or name.startswith(f"{start}.")]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend(dep for dep in graph.get(name, frozenset()) if dep not in seen)
    return frozenset(seen)


def _sources() -> list[Path]:
    files = sorted(PACKAGE.glob("*.py"))
    assert files, "the controller package is missing"
    return files


def test_no_controller_module_can_reach_the_code_that_writes_a_fact() -> None:
    reached = sorted(n for n in _reachable("edgar.controller") if n.startswith(FORBIDDEN))
    assert reached == [], f"the controller reaches memory through {reached}"


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_no_controller_module_names_a_hand_authored_file(source: Path) -> None:
    # Comments and docstrings may discuss AGENTS.md; only a string the code could
    # pass to open() is a problem, so the literals are read from the syntax tree.
    tree = ast.parse(source.read_text(encoding="utf-8"))
    docstrings = {
        ast.get_docstring(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    named = [text for text in literals if any(name in text for name in HAND_AUTHORED)]
    assert named == [], f"{source.name} names a hand-authored file: {named}"
