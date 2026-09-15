"""Finding extensions: `.edgar/extensions/*/` folders, user then project, enabled
by presence and disabled by name [EXT-2, EXT-3].

A found extension's `tools/`, `skills/` and `agents/` fold into the same
discovery results a plain project uses, keyed `extension:NAME` [EXT-8, TOOL-9].
Its `hooks.toml` is read by `extensions/hooks.py`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edgar.agents.discovery import Found as AgentsFound
from edgar.agents.discovery import scan as scan_agents
from edgar.core.errors import ConfigError
from edgar.extensions.manifest import Manifest, read
from edgar.skills.discovery import Found as SkillsFound
from edgar.skills.discovery import scan as scan_skills
from edgar.tools.custom import CommandTool, HttpTool
from edgar.tools.custom import load as load_custom


@dataclass
class Found:
    extensions: dict[str, Manifest] = field(default_factory=dict)  # by name, the winners
    tools: list[CommandTool | HttpTool] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def discover(
    root: Path, home: Path, skills: SkillsFound, agents: AgentsFound, disabled: tuple[str, ...] = ()
) -> Found:
    """Folds each extension's `skills/` and `agents/` straight into the plain
    project's own `skills`/`agents` results, so an extension's names win or lose
    a collision the same way a project skill would [TOOL-9]."""
    found = Found()
    scopes = [(home / ".edgar" / "extensions", "user"), (root / ".edgar" / "extensions", "project")]
    tool_folders: list[tuple[Path, str]] = []
    for base, origin in scopes:
        for folder in sorted(base.glob("*")) if base.is_dir() else []:
            if not folder.is_dir() or folder.name in disabled:
                continue
            _one(folder, origin, found, tool_folders, skills, agents)
    found.tools = load_custom(tool_folders)
    return found


def _one(
    folder: Path,
    origin: str,
    found: Found,
    tool_folders: list[tuple[Path, str]],
    skills: SkillsFound,
    agents: AgentsFound,
) -> None:
    try:
        manifest = read(folder)
    except ValueError as exc:
        found.problems.append(f"{folder}: {exc}")
        return
    old = found.extensions.get(manifest.name)
    if old is not None:
        found.warnings.append(f"the {origin} extension {manifest.name!r} replaces the earlier one")
    found.extensions[manifest.name] = manifest
    tagged = f"ext:{manifest.name}"  # [TOOL-1]'s origin convention for an extension
    tool_folders.append((folder / "tools", tagged))
    scan_skills(folder / "skills", tagged, skills)
    scan_agents(folder / "agents", tagged, agents)


def disabled_from_config(later: dict[str, Any]) -> tuple[str, ...]:
    """`[extensions] disabled = [...]` arrives in `Config.later["extensions"]` [EXT-3]."""
    raw = later.get("extensions", {})
    if not isinstance(raw, dict):
        raise ConfigError('[extensions] must be a table, written "[extensions]"')
    names = raw.get("disabled", [])
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ConfigError("[extensions] disabled must be a list of strings")
    return tuple(names)
