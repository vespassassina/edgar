"""Project trust: a cloned repository cannot run code on launch [PERM-13, CLI-19].

The executable parts of project config (command and HTTP tools in
`.edgar/tools/`, a `verify.command` from `.edgar/config.toml`; hooks, MCP servers
and extensions in v1) run only once the project is trusted. Trust is keyed by the
project's path and a hash of that config, stored in `~/.edgar/edgar.db`, and asked
again whenever the hash changes. User-scope config is always trusted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar.config.load import project_config
from edgar.config.schema import Config
from edgar.core.errors import ConfigError
from edgar.storage.db import Store


def executable(cwd: Path, config: Config) -> dict[str, str]:
    """What trusting this project would let run: a label for each, and its text."""
    found = {
        f"tool .edgar/tools/{p.name}": p.read_text(encoding="utf-8")
        for p in sorted((cwd / ".edgar" / "tools").glob("*.toml"))
    }
    if config.origins.get("verify.command") == str(project_config(cwd)):
        found["verify.command"] = config.verify.command or ""
    return found


def digest(items: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def store(home: Path) -> Store:
    return Store(home / ".edgar" / "edgar.db")


def trusted(cwd: Path, config: Config, home: Path) -> bool:
    items = executable(cwd, config)
    return not items or store(home).trusted(cwd, digest(items))


def require(cwd: Path, config: Config, home: Path) -> None:
    """The non-interactive check: untrusted executable config exits 3."""
    if not trusted(cwd, config, home):
        listed = ", ".join(executable(cwd, config))
        raise ConfigError(
            f"this project has executable config that is not trusted: {listed}",
            hint="review it, then run `edgar trust`; or pass --no-project-exec to run without it",
        )


def describe(cwd: Path, config: Config) -> str:
    items = executable(cwd, config)
    lines = [
        f"  {label}: {text.strip().splitlines()[0] if text.strip() else ''}"
        for label, text in items.items()
    ]
    return "\n".join([f"{cwd} has executable config:", *lines])


def trust(cwd: Path, config: Config, home: Path) -> None:
    store(home).trust(cwd, digest(executable(cwd, config)))
