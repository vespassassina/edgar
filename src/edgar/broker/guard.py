# TicketGuard: the mutable adapter tools/execute.py's pre_tool stage actually
# calls. It matches tools/base.py's `Broker` Protocol structurally -- Core
# never imports this file, only its shape.
# 1. check() runs the pure authorize() against the live ticket and clock.
# 2. A call the ticket allows counts toward `calls=`; a refused one does not,
#    since it never happened as far as the ticket's own budget is concerned.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edgar.broker.authorize import authorize
from edgar.broker.ticket import Ticket
from edgar.permissions.matcher import Subject


@dataclass(slots=True)
class TicketGuard:
    ticket: Ticket
    calls_so_far: int = 0

    def check(
        self, *, tool: str, read_only: bool, subject: Subject, cwd: Path
    ) -> tuple[str, str] | None:
        refusal = authorize(
            self.ticket,
            tool=tool,
            read_only=read_only,
            subject=subject,
            cwd=cwd,
            calls_so_far=self.calls_so_far,
            now=datetime.now(UTC),
        )
        if refusal is None:
            self.calls_so_far += 1
            return None
        return (refusal.caveat, refusal.reason)
