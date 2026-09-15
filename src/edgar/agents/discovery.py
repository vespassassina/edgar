"""Finding subagents: `.edgar/agents/*.md`, project over user [SUB-1, SUB-2]."""

# One flat file per agent, no bundled resources, unlike a skill's folder. The
# flow mirrors skills/discovery.py: user scope first, project second, so a
# project agent silently replaces a same-named user one, with a warning.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edgar.agents.definition import AgentBudget, AgentDefinition
from edgar.permissions.policy import MODES

_FRONT = re.compile(r"---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)", re.S)
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # same rule as a skill's name


@dataclass
class Found:
    agents: dict[str, AgentDefinition] = field(default_factory=dict)  # by name, the winners
    problems: list[str] = field(default_factory=list)  # files skipped, and why
    warnings: list[str] = field(default_factory=list)  # an agent replaced by another


def discover(root: Path, home: Path) -> Found:
    found = Found()
    scopes = [(home / ".edgar" / "agents", "user"), (root / ".edgar" / "agents", "project")]
    for folder, origin in scopes:
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                agent = _read(path, origin)
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                found.problems.append(f"{path}: {exc}")
                continue
            old = found.agents.get(agent.name)
            if old is not None:
                found.warnings.append(
                    f"the {origin} agent {agent.name!r} replaces the {old.origin} one"
                )
            found.agents[agent.name] = agent
    return found


def _read(path: Path, origin: str) -> AgentDefinition:
    import yaml  # lazy: a run with no agents never pays for it [NFR-1]

    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    if match is None:
        raise ValueError("no frontmatter: the file must open with a --- block")
    try:
        head = yaml.safe_load(match[1])
    except yaml.YAMLError as exc:
        raise ValueError(f"the frontmatter is not YAML: {exc}") from None
    if not isinstance(head, dict):
        raise ValueError("the frontmatter must be a mapping of keys to values")
    return _agent(head, match[2].strip(), path, origin)


def _agent(head: dict[str, Any], prompt: str, path: Path, origin: str) -> AgentDefinition:
    name, description = head.get("name"), head.get("description")
    if not isinstance(name, str) or not _NAME.match(name) or len(name) > 64:
        raise ValueError("`name` must be lowercase letters, digits and hyphens, up to 64")
    if name != path.stem:
        raise ValueError(f"`name` is {name!r} but the file is {path.name!r}")
    if not isinstance(description, str) or not 0 < len(description.strip()) <= 1024:
        raise ValueError("`description` must be text, 1 to 1,024 characters")
    mode = head.get("mode")
    if mode is not None and mode not in MODES:
        raise ValueError(f"`mode` must be one of {list(MODES)}")
    tools = head.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise ValueError("`tools` must be a list of tool names")
    budget_raw = head.get("budget", {})
    if not isinstance(budget_raw, dict):
        raise ValueError("`budget` must be a table, e.g. { cost = 0.10 }")
    max_turns = head.get("max_turns", 8)
    if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 1:
        raise ValueError("`max_turns` must be a positive integer")
    return AgentDefinition(
        name=name,
        description=" ".join(description.split()),
        path=path,
        model=head.get("model"),
        tools=tuple(tools),
        mode=mode,
        max_turns=max_turns,
        budget=AgentBudget(cost=budget_raw.get("cost"), turns=budget_raw.get("turns")),
        verify=head.get("verify"),
        prompt=prompt,
        origin=origin,
    )
