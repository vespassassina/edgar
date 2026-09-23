# 1. authorize(): pure, like permissions.decide() beside it [CAP-9]. No
#    caveats on the ticket -> nothing is refused, only the receipt is kept.
# 2. Each caveat kind is checked independently; the first one that refuses
#    wins, in the fixed order until, calls, tools, paths, hosts.
# 3. A `paths` or `hosts` caveat can only check tools that resolve to a path
#    or a URL. Anything it cannot check this way -- `shell`, and a command
#    tool not marked read-only -- is refused outright unless `tools=` names
#    it explicitly. That is the deliberate, visible cost of scoping a
#    session to files or hosts [ADR-0039].

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from edgar.broker.ticket import Ticket
from edgar.permissions.matcher import Subject


@dataclass(frozen=True, slots=True)
class Refusal:
    caveat: str
    reason: str


def authorize(
    ticket: Ticket,
    *,
    tool: str,
    read_only: bool,
    subject: Subject,
    cwd: Path,
    calls_so_far: int,
    now: datetime,
) -> Refusal | None:
    by_kind = {c.kind: c.value for c in ticket.caveats}

    until = by_kind.get("until")
    if until is not None and now > datetime.fromisoformat(until):
        return Refusal("until", f"the ticket expired at {until}")

    calls_cap = by_kind.get("calls")
    if calls_cap is not None and calls_so_far >= int(calls_cap):
        return Refusal("calls", f"the ticket allows at most {calls_cap} calls")

    tools_cap = by_kind.get("tools")
    named = tools_cap is not None and _in_list(tools_cap, tool)
    if tools_cap is not None and not named:
        return Refusal("tools", f"{tool} is not in tools={tools_cap}")

    paths_cap = by_kind.get("paths")
    hosts_cap = by_kind.get("hosts")
    is_url = _looks_like_url(subject.text)

    if (
        paths_cap is not None
        and subject.path is not None
        and not _path_matches(paths_cap, subject.path, cwd)
    ):
        return Refusal("paths", f"{subject.text} is not under paths={paths_cap}")

    if (
        hosts_cap is not None
        and is_url
        and not _in_list(hosts_cap, urlparse(subject.text).hostname or "")
    ):
        return Refusal("hosts", f"{subject.text} is not in hosts={hosts_cap}")

    unchecked = subject.path is None and not is_url
    if (
        (paths_cap is not None or hosts_cap is not None)
        and not read_only
        and unchecked
        and not named
    ):
        caveat = "paths" if paths_cap is not None else "hosts"
        return Refusal(
            caveat, f"{tool} cannot be checked against {caveat}=; name it in tools= to allow it"
        )

    return None


def _in_list(csv: str, name: str) -> bool:
    return name in (item.strip() for item in csv.split(","))


def _path_matches(csv: str, path: Path, cwd: Path) -> bool:
    resolved = str(path)
    for pattern in (p.strip() for p in csv.split(",") if p.strip()):
        target = pattern if pattern.startswith("/") else str((cwd / pattern).resolve())
        if resolved == target or fnmatch.fnmatch(resolved, target):
            return True
    return False


def _looks_like_url(text: str) -> bool:
    parsed = urlparse(text)
    return bool(parsed.scheme) and bool(parsed.netloc)
