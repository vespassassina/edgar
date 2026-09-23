# edgar.broker is v4, and removable: nothing in Core, v1, v2 or v3 imports it, a
# test proves it, and CI deletes the package and runs the suite below it [NFR-12].
# cli/setup.py reaches from_scope() and describe() below by name, through
# import_module, the same way it reaches escalation and the controller
# [ADR-0015]. attach() -- the receipt subscriber and Intents -- still lands
# with the receipt module [ADR-0039].

from __future__ import annotations

from collections.abc import Iterable

from edgar.broker.caveats import parse_scope
from edgar.broker.guard import TicketGuard
from edgar.broker.ticket import Ticket
from edgar.core.session import new_id


def from_scope(pairs: Iterable[str]) -> TicketGuard:
    """A live ticket from `--scope`/`/scope` KEY=VALUE pairs [CAP-1, CAP-2]."""
    return TicketGuard(Ticket(intent_id=new_id(), caveats=parse_scope(pairs)))


def describe(guard: TicketGuard | None) -> str:
    """A one-line summary for `/scope` with no argument."""
    if guard is None:
        return "no scope set: every tool call the mode allows may run [CAP-3]"
    if not guard.ticket.caveats:
        return "scope set with no caveats: every tool call the mode allows may run"
    return "scope: " + ", ".join(f"{c.kind}={c.value}" for c in guard.ticket.caveats)
