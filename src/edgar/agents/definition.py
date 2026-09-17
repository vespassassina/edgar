"""A subagent's definition: markdown + YAML frontmatter [SUB-1].

The same shape as a skill (`skills/discovery.py`): frontmatter is what
discovery reads, the body is the agent's own system prompt, loaded only when
`agents/spawn.py` actually starts it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from edgar.config.schema import Mode

ISOLATIONS = ("none", "worktree")  # [SUB-11]


@dataclass(frozen=True, slots=True)
class AgentBudget:
    cost: float | None = None  # USD; None: inherit the parent's remainder [SUB-7]
    turns: int | None = None


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    description: str  # what the `task` tool schema shows the model
    path: Path
    model: str | None = None  # None: routing picks one for role "subagent" [ROUTE-1]
    tools: tuple[str, ...] = ()  # empty: every tool the parent's registry has
    mode: Mode | None = None  # None: inherit the parent's; never widens it [PERM-8]
    max_turns: int = 8
    budget: AgentBudget = field(default_factory=AgentBudget)
    verify: str | None = None  # a shell command, run like [verify] command [VER-1]
    isolation: str = "none"  # "worktree" runs it in its own git worktree [SUB-11]
    prompt: str = ""  # the body: the agent's own instructions
    origin: str = "project"  # "user" or "project" [SUB-2]
