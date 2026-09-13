"""`edgar trust` and `edgar permissions list|revoke`: what a human decided, shown
and changed by a human [PERM-6, PERM-13, CLI-19]."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from edgar.cli import trust
from edgar.config.load import load
from edgar.storage.db import Store

USAGE = "usage: edgar trust [--yes] | edgar permissions list | edgar permissions revoke ID"


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    if argv[0] == "trust" and set(argv[1:]) <= {"--yes"}:
        config = load(cwd, home=home)
        if not trust.executable(cwd, config):
            print("nothing to trust: this project declares no executable config")
            return 0
        print(trust.describe(cwd, config))
        if "--yes" not in argv and input("trust it? [y/N] ").strip().lower() != "y":
            return 1
        trust.trust(cwd, config, home)
        print(f"trusted {cwd}; a change to that config asks again")
        return 0
    grants = Store(cwd / ".edgar" / "edgar.db")
    if argv[1:] == ["list"]:
        for grant_id, tool, subject, created in grants.grants():
            when = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
            print(f"{grant_id:>4}  {when}  {tool:<10} {subject}")
        return 0
    if len(argv) == 3 and argv[1] == "revoke" and argv[2].isdigit():
        if grants.revoke(int(argv[2])):
            print(f"revoked {argv[2]}")
            return 0
        print(f"no grant {argv[2]}", file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2
