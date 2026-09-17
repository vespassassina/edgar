"""`isolation: worktree`: a write-capable subagent works in its own git worktree,
on its own branch, and never touches the parent's working copy [SUB-11].
"""

# One isolated subagent, as pseudocode:
#
#   create(cwd, agent, session):
#     ask git for the repository root                    refuse if there is none
#     git worktree add -b edgar/<agent>-<session> under .edgar/worktrees/
#     remember the commit it was cut from                     so `finish` can diff
#   ... the subagent runs with its `cwd` there, so every path rule the permission
#       engine applies is rebased with it: the parent's files are simply outside
#       the working directory and stay Ask [PERM-3] ...
#   finish(tree):
#     diff against that commit                        the stat line for the summary
#     git status --porcelain
#       anything there -> KEEP the tree, name it and say how to reach it
#       nothing there  -> git worktree remove, plain, never --force; the branch
#                         keeps whatever the subagent committed
#
# Two things this deliberately does not do. It never passes `--force`, to git or
# to anything else, so uncommitted work is never destroyed by the harness: the
# worst case is a worktree left on disk with its name in the summary. And it
# never falls back to running unisolated, because an agent whose frontmatter asks
# for a worktree and silently does not get one is worse than one that refuses.
#
# A worktree is cut from the parent's HEAD *commit*, so the parent's own
# uncommitted changes are never carried into it and never at risk.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from edgar.tools.builtin.shell import run_argv

ISOLATION = "worktree"
_BRANCH = "edgar/"  # every branch this makes is namespaced, so `git branch` reads clearly


@dataclass(frozen=True, slots=True)
class Worktree:
    path: Path  # .edgar/worktrees/<agent>-<session>, the subagent's cwd
    branch: str
    base: str  # the commit it was cut from, for the closing diff
    root: Path  # the parent repository, where `git worktree remove` is run from


async def _git(*argv: str, cwd: Path) -> tuple[int, str]:
    # git is the only program this module runs, through the same launcher as
    # `shell`, so a cancelled turn takes it down with its children too.
    try:
        return await run_argv(["git", *argv], cwd)
    except (FileNotFoundError, NotADirectoryError):
        return 127, "git is not installed or not on PATH"


async def create(cwd: Path, agent: str, session: str) -> tuple[Worktree | None, str]:
    """The worktree, or None and the refusal to hand back to the model."""
    # 1. Outside a repository there is nothing to isolate. Refuse, loudly.
    code, out = await _git("rev-parse", "--show-toplevel", cwd=cwd)
    if code:
        return None, (
            f"agent {agent!r} asks for `isolation: worktree`, but {cwd} is not inside a "
            f"git repository, so there is no worktree to make and the agent was not "
            f"run ({out.strip()}). Run it from a repository, or drop `isolation` from "
            f"its frontmatter to let it share this working copy."
        )
    root = Path(out.strip())
    name = f"{agent}-{session}"
    path = root / ".edgar" / "worktrees" / name
    branch = f"{_BRANCH}{name}"
    # 2. A new branch and a new tree, both named after the agent and the session.
    code, out = await _git("worktree", "add", "-b", branch, str(path), "HEAD", cwd=root)
    if code:
        return None, (
            f"agent {agent!r} asks for `isolation: worktree`, but git could not make "
            f"one at {path} and the agent was not run: {out.strip()}"
        )
    # 3. The commit it was cut from: what `finish` measures the subagent against.
    _, head = await _git("rev-parse", "HEAD", cwd=path)
    return Worktree(path, branch, head.strip() or "HEAD", root), ""


async def finish(tree: Worktree) -> str:
    """What the subagent changed, and what happened to its worktree."""
    # 1. The diff stat covers tracked changes, committed or not; porcelain also
    #    sees new files, which is why both are read.
    _, stat = await _git("diff", "--stat", tree.base, cwd=tree.path)
    _, porcelain = await _git("status", "--porcelain", cwd=tree.path)
    pending = [line for line in porcelain.splitlines() if line.strip()]
    changed = stat.strip().splitlines()[-1].strip() if stat.strip() else "no tracked file changed"
    head = f"branch {tree.branch}: {changed}"
    # 2. Uncommitted or untracked work: the tree stays, and the human is told where.
    if pending:
        return (
            f"{head}; {len(pending)} uncommitted change(s), so the worktree was KEPT at "
            f"{tree.path}. Read it with `git -C {tree.path} status`, and delete it with "
            f"`git worktree remove {tree.path}` once you no longer want it."
        )
    # 3. Clean: the branch already holds anything that was committed, so the tree goes.
    code, out = await _git("worktree", "remove", str(tree.path), cwd=tree.root)
    if code:
        return f"{head}; the worktree was KEPT at {tree.path}: {out.strip()}"
    return f"{head}; the worktree was removed, and the branch keeps what it committed."
