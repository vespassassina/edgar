"""`edgar doctor`: what this machine and this project would do to a session
[CFG-5], finished in M22 with the checks ADR-0053 cut from 1.0.

Every line says what was checked, what was found and what to do about it. The
whole run is offline unless `--network` is given: the checks below read the
config, the filesystem and `PATH`, and nothing else.
"""

# The checks, in the order they print:
#
#   project/home   a cloud-synced folder, where SQLite wants care [CFG-5]
#   sandbox        what [shell] sandbox is set to, and the best backend here
#   trust          this project's executable config, and whether it is trusted
#   db             PRAGMA integrity_check on the project's DB and the user's
#   mcp            each [mcp.NAME]: a local server's program on PATH, a remote's URL
#   ext            each extension's requires.commands, on PATH or missing
#   cred           each provider's endpoint and whether its key variable is set
#   conn           --network only: each provider's endpoint, asked for its models
#
# Two deliberate limits, both named in the output rather than hidden:
#
# - A *remote* MCP server is not probed. The only probe that means anything for
#   one is the handshake, which `edgar mcp test NAME` already performs and which
#   may need a token; doctor points at it instead of inventing a second, weaker
#   answer. A *local* one is checked the one way that costs nothing and cannot
#   hang: is the program it names on PATH.
# - `conn` is the adapter's own `models()` call. It is behind `--network`
#   because a diagnostic must not reach the network unasked, and because for
#   most providers it needs that provider's key. It lists models rather than
#   generating, so it costs no tokens.
#
# Tick installation [SCH-*] is not checked: scheduling is M16, v4, and nothing
# installs a tick yet. The line arrives with the feature.

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
from pathlib import Path

from edgar.cli import trust
from edgar.cli.models import describe
from edgar.cli.setup import toolset
from edgar.config.load import load
from edgar.config.schema import Config
from edgar.core.errors import EdgarError
from edgar.providers.registry import BUILTIN, resolve
from edgar.sandbox.base import best

CLOUD = ("icloud", "mobile documents", "onedrive", "dropbox", "google drive", "my drive")


def command(cwd: Path, home: Path | None = None, *, network: bool = False) -> int:
    home = home or Path.home()
    config = load(cwd, home=home)
    for path, label in ((cwd, "project"), (home, "home")):
        hit = next((c for c in CLOUD if c in str(path.resolve()).lower()), None)
        tag = f"syncs through {hit}; SQLite there wants care [CFG-5]" if hit else "ok"
        print(f"{label:<8} {path}  {tag}")
    # What `[shell] sandbox` is set to, and the strongest backend that really runs
    # here. A recommendation, never a change: edgar confines nothing you did not ask
    # it to confine [PERM-15].
    now, could = config.shell.sandbox, best()
    advice = "ok" if now == could else f"set [shell] sandbox = {could!r} for a real sandbox"
    print(f"sandbox  {now:<11} best available here: {could}; {advice}")
    _trust(cwd, config, home)
    _db(cwd, home)
    _mcp(config)
    _ext(cwd, home, config)
    names = sorted({*BUILTIN, *config.providers} - {"fake"})
    for name in names:
        print(f"cred     {name:<11} {describe(name, config, os.environ)}")
    if not network:
        print(f"conn     {'(skipped)':<11} pass --network to ask each endpoint for its models")
        return 0
    asyncio.run(_connectivity(names, config))
    return 0


def _trust(cwd: Path, config: Config, home: Path) -> None:
    # Whether this project's executable config would run [PERM-13]. Untrusted is
    # not a fault: it is the safe state, and the line says how to leave it.
    items = trust.executable(cwd, config)
    if not items:
        print(f"trust    {'n/a':<11} this project declares no executable config")
    elif trust.trusted(cwd, config, home):
        print(f"trust    {'trusted':<11} {', '.join(items)}; a change to it asks again")
    else:
        print(f"trust    {'untrusted':<11} {', '.join(items)}; review it, then `edgar trust`")


def _db(cwd: Path, home: Path) -> None:
    # SQLite's own verdict on each store [CFG-5]. A file that is not there yet is
    # not a problem: the first session writes it.
    for base, label in ((cwd, "project"), (home, "user")):
        path = base / ".edgar" / "edgar.db"
        if not path.exists():
            print(f"db       {label:<11} not written yet; the first session creates it")
            continue
        try:
            with sqlite3.connect(path) as db:
                said = str(db.execute("PRAGMA integrity_check").fetchone()[0])
        except sqlite3.Error as exc:
            said = str(exc)
        if said == "ok":
            print(f"db       {label:<11} integrity_check ok: {path}")
        else:
            print(f"db       {label:<11} {said}; move {path} aside and edgar writes a new one")


def _mcp(config: Config) -> None:
    # A local server is a program: the check is whether it is on PATH. A remote one
    # is a host, and only the handshake tells you anything, so this points at it.
    for name, block in config.mcp.items():
        if block.command is None:
            print(f"mcp      {name:<11} remote {block.url}; `edgar mcp test {name}` tries it")
            continue
        where = shutil.which(block.command)
        if where:
            print(f"mcp      {name:<11} {block.command} on PATH: {where}")
        else:
            print(
                f"mcp      {name:<11} {block.command} is not on PATH; install it or fix the block"
            )


def _ext(cwd: Path, home: Path, config: Config) -> None:
    # Each extension's `requires.commands` [EXT-1]: a bundle whose tools call a
    # program that is not here fails at the first call, which is far too late.
    trusted = trust.trusted(cwd, config, home)
    _, _, _, _, ext = toolset(cwd, home, config, project_exec=trusted)
    for manifest in ext.extensions.values():
        wanted = manifest.requires_commands
        missing = [c for c in wanted if shutil.which(c) is None]
        if missing:
            print(f"ext      {manifest.name:<11} {', '.join(missing)} not on PATH; install them")
        else:
            print(f"ext      {manifest.name:<11} {len(wanted)} required commands, all on PATH")


async def _connectivity(names: list[str], config: Config) -> None:
    for name in names:
        try:
            provider, _ = resolve(f"{name}/-", config)
            await provider.models()
        except EdgarError as exc:
            print(f"conn     {name:<11} {exc}")
        else:
            print(f"conn     {name:<11} ok")
