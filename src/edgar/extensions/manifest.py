"""Extension manifests: `extension.toml` in a folder alongside `tools/`, `skills/`,
`agents/`, `hooks.toml` and `mcp.toml` [EXT-1]."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # same rule as a skill's name


@dataclass(frozen=True, slots=True)
class Manifest:
    name: str
    version: str
    description: str
    path: Path
    requires_edgar: str | None = None
    requires_commands: tuple[str, ...] = field(default_factory=tuple)


def read(folder: Path) -> Manifest:
    """Raises ValueError; the caller turns that into a discovery problem."""
    try:
        data = tomllib.loads((folder / "extension.toml").read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read extension.toml: {exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"extension.toml is not valid TOML: {exc}") from None
    name, version, description = data.get("name"), data.get("version"), data.get("description")
    if not isinstance(name, str) or not _NAME.match(name) or name != folder.name:
        raise ValueError(f"`name` must match the folder name {folder.name!r}")
    if not isinstance(version, str) or not version:
        raise ValueError("`version` must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("`description` must be non-empty text")
    requires = data.get("requires", {})
    if not isinstance(requires, dict):
        raise ValueError('`requires` must be a table, e.g. { edgar = ">=1.0" }')
    commands = requires.get("commands", [])
    if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
        raise ValueError("`requires.commands` must be a list of strings")
    edgar_req = requires.get("edgar")
    if edgar_req is not None and not isinstance(edgar_req, str):
        raise ValueError("`requires.edgar` must be a version string")
    return Manifest(
        name, version, " ".join(description.split()), folder, edgar_req, tuple(commands)
    )
