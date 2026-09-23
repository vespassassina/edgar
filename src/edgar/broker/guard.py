# TicketGuard: the mutable adapter tools/execute.py's pre_tool stage actually
# calls. It matches tools/base.py's `Broker` Protocol structurally -- Core
# never imports this file, only its shape.
# 1. check() runs the pure authorize() against the live ticket and clock.
# 2. A call the ticket allows counts toward `calls=`; a refused one does not,
#    since it never happened as far as the ticket's own budget is concerned.
# 3. narrowed() is `task`'s delegation seam: agents/spawn.py calls it with the
#    agent definition's own `tools:` and any `scope` argument the model gave.
#    Both can only add caveats, via attenuate(), never drop one [CAP-5].
# 4. tighten() is the controller's seam (CTRL-8): the same attenuate(), on the
#    live ticket in place rather than a fresh guard, since the session already
#    holds this one.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edgar.broker.authorize import authorize
from edgar.broker.caveats import Caveat, parse_scope
from edgar.broker.ticket import Ticket, attenuate
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

    def narrowed(
        self, *, subject: str, tools: tuple[str, ...], scope: tuple[str, ...]
    ) -> TicketGuard:
        extra = parse_scope(scope)
        if tools:
            extra = (*extra, Caveat(kind="tools", value=",".join(tools)))
        return TicketGuard(attenuate(self.ticket, subject=subject, extra=extra))

    def tighten(self, extra: tuple[Caveat, ...]) -> None:
        self.ticket = attenuate(self.ticket, subject=self.ticket.subject, extra=extra)
