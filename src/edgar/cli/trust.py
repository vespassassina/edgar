"""Project trust: a cloned repository cannot run code on launch [PERM-13, CLI-19].

The executable parts of project config (command and HTTP tools in
`.edgar/tools/`, a `verify.command`, an `[mcp.NAME]` server or a `[browser]`
command from `.edgar/config.toml`; hooks and extensions in M10) run only once the
project is trusted. Trust is keyed by the
project's path and a hash of that config, stored in `~/.edgar/edgar.db`, and asked
again whenever the hash changes. User-scope config is always trusted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
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
    if from_project(config, cwd, "verify.command"):
        found["verify.command"] = config.verify.command or ""
    for name, block in config.mcp.items():  # a server is a program, or a host [TOOL-7]
        if from_project(config, cwd, f"mcp.{name}."):
            found[f"mcp server {name}"] = json.dumps(asdict(block), sort_keys=True)
    if from_project(config, cwd, "browser."):  # what /browser would start [CLI-29]
        found["browser"] = json.dumps(asdict(config.browser), sort_keys=True)
    return found


def from_project(config: Config, cwd: Path, prefix: str) -> bool:
    """True when this project's config.toml set any key under `prefix` [CFG-2]."""
    where = str(project_config(cwd))
    return any(k.startswith(prefix) and v == where for k, v in config.origins.items())


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
