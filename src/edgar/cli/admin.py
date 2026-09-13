"""The subcommands that look at a project rather than run a turn: `edgar trust`
and `edgar permissions list|revoke`, what a human decided, shown and changed by a
human [PERM-6, PERM-13, CLI-19]; `edgar sessions list|show|rm` [CLI-11]."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from edgar.cli import trust
from edgar.config.load import load
from edgar.context.tokens import message_text
from edgar.storage.db import Store
from edgar.storage.transcript import conversation, find, listing

USAGE = """usage: edgar trust [--yes] | edgar permissions list | edgar permissions revoke ID
       edgar sessions list | show ID | rm ID"""


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    if argv[0] == "sessions" and len(argv) in (2, 3):
        return _sessions(argv[1:], cwd)
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


def _sessions(argv: list[str], cwd: Path) -> int:
    if argv == ["list"]:
        print("\n".join(listing(cwd)) or "no sessions yet")
    elif argv[0] == "show" and len(argv) == 2:
        for message in conversation(find(cwd, argv[1])):
            print(f"{message.role}: {message_text(message)}\n")
    elif argv[0] == "rm" and len(argv) == 2:
        path = find(cwd, argv[1])
        shutil.rmtree(path.with_suffix(""), ignore_errors=True)  # its blobs
        path.unlink()
        print(f"removed {path.stem}")
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0
