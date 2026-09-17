"""Subagent definitions: discovery and validation [SUB-1, SUB-2]."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from edgar.agents.definition import AgentBudget, AgentDefinition
from edgar.agents.discovery import discover


def _agent(
    scope: Path,
    name: str,
    description: str = "Use when testing.",
    body: str = "",
    extra: str = "",
) -> Path:
    scope.mkdir(parents=True, exist_ok=True)
    head = f"---\nname: {name}\ndescription: {description}\n{extra}---\n"
    text = f"{head}{body or f'The {name} body.'}\n"
    path = scope / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _project(root: Path) -> Path:
    return root / ".edgar" / "agents"


def _user(home: Path) -> Path:
    return home / ".edgar" / "agents"


# definition [SUB-1]


def test_agent_definition_defaults() -> None:
    agent = AgentDefinition(name="reviewer", description="Reviews code.", path=Path("x.md"))
    assert agent.model is None
    assert agent.tools == ()
    assert agent.mode is None
    assert agent.max_turns == 8
    assert agent.budget == AgentBudget()
    assert agent.verify is None
    assert agent.isolation == "none"
    assert agent.origin == "project"


def test_isolation_is_read_from_the_frontmatter(tmp_project: Path, home: Path) -> None:
    _agent(_project(tmp_project), "walled", extra="isolation: worktree\n")
    assert discover(tmp_project, home).agents["walled"].isolation == "worktree"  # [SUB-11]


# discovery [SUB-1, SUB-2]


def test_discovery_reads_the_frontmatter_of_each_scope(tmp_project: Path, home: Path) -> None:
    _agent(_project(tmp_project), "reviewer", "Use when reviewing.")
    _agent(_user(home), "planner", "Use when planning\n  a task.")
    found = discover(tmp_project, home)
    assert sorted(found.agents) == ["planner", "reviewer"]
    assert found.agents["planner"].description == "Use when planning a task."  # one line
    assert found.agents["reviewer"].origin == "project"
    assert found.agents["planner"].origin == "user"
    assert found.problems == found.warnings == []


def test_the_project_wins_and_says_so(tmp_project: Path, home: Path) -> None:
    _agent(_user(home), "reviewer", "user")
    _agent(_project(tmp_project), "reviewer", "project")
    found = discover(tmp_project, home)
    assert found.agents["reviewer"].description == "project"
    assert found.warnings == ["the project agent 'reviewer' replaces the user one"]


def test_full_frontmatter_is_parsed(tmp_project: Path, home: Path) -> None:
    extra = (
        "model: anthropic/claude-haiku-4-5\n"
        "tools:\n  - read\n  - write\n"
        "mode: auto\n"
        "max_turns: 3\n"
        "budget:\n  cost: 0.10\n  turns: 2\n"
        "verify: pytest -q\n"
    )
    _agent(_project(tmp_project), "reviewer", body="Review things carefully.", extra=extra)
    found = discover(tmp_project, home)
    agent = found.agents["reviewer"]
    assert agent.model == "anthropic/claude-haiku-4-5"
    assert agent.tools == ("read", "write")
    assert agent.mode == "auto"
    assert agent.max_turns == 3
    assert agent.budget == AgentBudget(cost=0.10, turns=2)
    assert agent.verify == "pytest -q"
    assert agent.prompt == "Review things carefully."


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("no frontmatter here\n", "no frontmatter"),
        ("---\nname: [unclosed\n---\n", "not YAML"),
        ("---\n- a list\n---\n", "mapping"),
        ("---\nname: Bad_Name\ndescription: x\n---\n", "lowercase"),
        ("---\nname: other\ndescription: x\n---\n", "the file is 'broken.md'"),
        ("---\nname: broken\n---\n", "description"),
        ("---\nname: broken\ndescription: x\nmode: not-a-mode\n---\n", "mode"),
        ("---\nname: broken\ndescription: x\ntools: nope\n---\n", "tools"),
        ("---\nname: broken\ndescription: x\nbudget: nope\n---\n", "budget"),
        ("---\nname: broken\ndescription: x\nmax_turns: 0\n---\n", "max_turns"),
        # An author who asks for isolation never silently gets none [SUB-11].
        ("---\nname: broken\ndescription: x\nisolation: sandbox\n---\n", "isolation"),
    ],
)
def test_a_broken_agent_is_skipped_with_its_reason(
    tmp_project: Path, home: Path, text: str, problem: str
) -> None:
    folder = _project(tmp_project)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "broken.md").write_text(text, encoding="utf-8")
    _agent(folder, "fine")
    found = discover(tmp_project, home)
    assert list(found.agents) == ["fine"]
    assert len(found.problems) == 1 and problem in found.problems[0]


def test_finding_no_agents_never_imports_yaml(tmp_project: Path, home: Path) -> None:
    code = (
        "import sys; from pathlib import Path; from edgar.agents.discovery import discover; "
        f"discover(Path({str(tmp_project)!r}), Path({str(home)!r})); "
        "sys.exit('yaml' in sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0  # [NFR-1]
