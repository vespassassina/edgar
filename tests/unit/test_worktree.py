"""Worktree subagents: two branches, an untouched parent, and a dirty tree kept [SUB-11].

These drive real `git`, because what is being tested is what git does. `git` is a
subprocess, not a socket, so the suite-wide `no_network` fixture is happy with it.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest
from harness import guard

from edgar.agents.definition import AgentDefinition
from edgar.agents.spawn import SpawnLimits, spawn
from edgar.agents.worktree import Worktree, create, finish
from edgar.config.schema import Config, ModelSection
from edgar.core.events import EventBus
from edgar.tools.base import ToolContext, ToolResult
from edgar.tools.registry import core_registry


def git(*argv: str, cwd: Path) -> str:
    done = subprocess.run(["git", *argv], cwd=cwd, capture_output=True, text=True, check=False)
    return (done.stdout + done.stderr).strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A one-commit repository that ignores `.edgar/`, as `edgar init` leaves one."""
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "-q", cwd=root)
    git("config", "user.email", "t@example.com", cwd=root)
    git("config", "user.name", "Test", cwd=root)
    (root / "shared.txt").write_text("base\n", encoding="utf-8")
    (root / ".gitignore").write_text(".edgar/\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-qm", "init", cwd=root)
    return root


def made(root: Path, agent: str, session: str) -> Worktree:
    tree, refusal = asyncio.run(create(root, agent, session))
    assert tree is not None, refusal
    return tree


def test_create_refuses_outside_a_git_repository(tmp_path: Path) -> None:
    tree, refusal = asyncio.run(create(tmp_path, "helper", "S1"))

    assert tree is None
    assert "not inside a git repository" in refusal
    assert "was not run" in refusal  # it says the agent did not run unisolated


def test_two_agents_write_the_same_file_on_two_branches(repo: Path) -> None:
    one, two = made(repo, "alpha", "S1"), made(repo, "beta", "S2")

    for tree, text in ((one, "alpha wrote this\n"), (two, "beta wrote this\n")):
        (tree.path / "shared.txt").write_text(text, encoding="utf-8")

    # Neither subagent saw the other's edit, and neither reached the parent's copy.
    assert (one.path / "shared.txt").read_text() == "alpha wrote this\n"
    assert (two.path / "shared.txt").read_text() == "beta wrote this\n"
    assert (repo / "shared.txt").read_text() == "base\n"
    assert git("status", "--porcelain", cwd=repo) == ""
    assert one.branch != two.branch
    assert {one.branch, two.branch} == {"edgar/alpha-S1", "edgar/beta-S2"}


def test_a_worktree_is_cut_from_head_so_the_parents_own_edits_are_never_at_risk(
    repo: Path,
) -> None:
    (repo / "shared.txt").write_text("base\nthe human is mid-edit\n", encoding="utf-8")

    tree = made(repo, "helper", "S1")

    assert (tree.path / "shared.txt").read_text() == "base\n"  # HEAD, not the dirty tree
    assert (repo / "shared.txt").read_text() == "base\nthe human is mid-edit\n"


def test_a_dirty_worktree_is_kept_and_named(repo: Path) -> None:
    tree = made(repo, "helper", "S1")
    (tree.path / "shared.txt").write_text("half-finished\n", encoding="utf-8")

    summary = asyncio.run(finish(tree))

    assert "KEPT" in summary
    assert str(tree.path) in summary and tree.branch in summary
    assert "git worktree remove" in summary  # how a human gets rid of it later
    assert tree.path.is_dir() and (tree.path / "shared.txt").read_text() == "half-finished\n"


def test_an_untracked_file_alone_keeps_the_worktree(repo: Path) -> None:
    tree = made(repo, "helper", "S1")
    (tree.path / "brand-new.txt").write_text("never committed\n", encoding="utf-8")

    summary = asyncio.run(finish(tree))

    assert "KEPT" in summary
    assert (tree.path / "brand-new.txt").is_file()


def test_a_clean_worktree_is_removed_and_its_branch_survives(repo: Path) -> None:
    tree = made(repo, "helper", "S1")
    (tree.path / "shared.txt").write_text("committed work\n", encoding="utf-8")
    git("add", "-A", cwd=tree.path)
    git("commit", "-qm", "the subagent's work", cwd=tree.path)

    summary = asyncio.run(finish(tree))

    assert "removed" in summary and "KEPT" not in summary
    assert tree.branch in summary and "1 file changed" in summary
    assert not tree.path.exists()
    assert tree.branch in git("branch", "--list", tree.branch, cwd=repo)
    assert "committed work" in git("show", f"{tree.branch}:shared.txt", cwd=repo)


# Through `spawn`, which is where a frontmatter `isolation:` actually bites.


def _spawn(root: Path, task: str, isolation: str) -> ToolResult:
    agent = AgentDefinition(
        name="helper",
        description="Helps.",
        path=Path("helper.md"),
        prompt="Help.",
        isolation=isolation,
    )
    ctx = ToolContext(cwd=root, bus=EventBus(), blob_dir=root / "blobs", max_output_tokens=8000)
    return asyncio.run(
        spawn(
            agent,
            task,
            ctx=ctx,
            limits=SpawnLimits(),
            config=Config(model=ModelSection(default="fake/test")),
            env=None,
            registry=core_registry(),
            guard=guard(root, mode="auto"),
        )
    )


def test_spawn_runs_a_worktree_agent_with_its_cwd_rebased(repo: Path) -> None:
    (repo / "shared.txt").write_text("base\nthe human is mid-edit\n", encoding="utf-8")

    result = _spawn(repo, "read shared.txt", "worktree")

    assert result.error is None
    assert "base\n" in result.text and "mid-edit" not in result.text  # it read its own copy
    assert "branch edgar/helper-" in result.text and "removed" in result.text
    assert (repo / "shared.txt").read_text() == "base\nthe human is mid-edit\n"


def test_spawn_refuses_a_worktree_agent_outside_a_repository(tmp_project: Path) -> None:
    result = _spawn(tmp_project, "read a.txt", "worktree")

    assert result.error == "validation"
    assert "not inside a git repository" in result.text
    assert "hello" not in result.text  # it never ran the task unisolated


def test_spawn_leaves_a_plain_agent_in_the_parents_tree(tmp_project: Path) -> None:
    result = _spawn(tmp_project, "read a.txt", "none")

    assert result.error is None and "hello" in result.text
    assert "branch edgar/" not in result.text


def test_session_state_under_the_worktree_does_not_make_it_dirty(repo: Path) -> None:
    # The subagent's own JSONL and blobs land in `<tree>/.edgar/`, which the
    # project ignores; if it did not, the tree would read dirty and be kept.
    tree = made(repo, "helper", "S1")
    (tree.path / ".edgar" / "sessions" / "S1").mkdir(parents=True)
    (tree.path / ".edgar" / "sessions" / "S1" / "s.jsonl").write_text("{}\n", encoding="utf-8")

    summary = asyncio.run(finish(tree))

    assert "removed" in summary and not tree.path.exists()
