"""`edgar doctor`: credentials, connectivity, and a cloud-synced-folder warning
[CFG-5]. MCP, extension, trust, tick and DB-integrity checks, and `--network`,
move to v2 (ADR-0053); no sandbox recommendation either, since only `none`
exists in v1 (ADR-0050)."""

# Cloud detection is a substring match on the resolved path: catches OneDrive,
# Dropbox and Google Drive (each keeps its name in the path) and iCloud Drive
# used deliberately, but not macOS's silent Desktop & Documents sync, which
# leaves ~/Documents looking ordinary — a known gap, named rather than hidden.

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from edgar.cli.models import describe
from edgar.config.load import load
from edgar.config.schema import Config
from edgar.core.errors import EdgarError
from edgar.providers.registry import BUILTIN, resolve

CLOUD = ("icloud", "mobile documents", "onedrive", "dropbox", "google drive", "my drive")


def command(cwd: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    config = load(cwd, home=home)
    for path, label in ((cwd, "project"), (home, "home")):
        hit = next((c for c in CLOUD if c in str(path.resolve()).lower()), None)
        tag = f"syncs through {hit}; SQLite there wants care [CFG-5]" if hit else "ok"
        print(f"{label:<8} {path}  {tag}")
    names = sorted({*BUILTIN, *config.providers} - {"fake"})
    for name in names:
        print(f"cred     {name:<11} {describe(name, config, os.environ)}")
    asyncio.run(_connectivity(names, config))
    return 0


async def _connectivity(names: list[str], config: Config) -> None:
    for name in names:
        try:
            provider, _ = resolve(f"{name}/-", config)
            await provider.models()
        except EdgarError as exc:
            print(f"conn     {name:<11} {exc}")
        else:
            print(f"conn     {name:<11} ok")
