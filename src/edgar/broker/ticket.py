# 1. Ticket: what one intent may do, carrying its own chain of custody.
# 2. attenuate() is the only way to get a child ticket. For a list-shaped
#    caveat (tools, paths, hosts) it can only add items; for calls or until
#    it can only tighten, never loosen, since those are single limits, not
#    lists -- so "merge" means "narrow" for the two of them.
# 3. verify_chain() walks the parent links and fails the moment a child's
#    caveats are not at least as strict as its parent's, so a forged or
#    edited delegation cannot verify [CAP-5]. It compares the meaning of
#    each kind (list superset, or tighter limit), not raw Caveat equality,
#    because attenuate() legitimately rewrites a caveat's value string.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edgar.broker.caveats import Caveat, Kind

_LIST_KINDS: tuple[Kind, ...] = ("tools", "paths", "hosts")


@dataclass(frozen=True, slots=True)
class Ticket:
    intent_id: str
    subject: str = "main"
    caveats: tuple[Caveat, ...] = ()
    parent: Ticket | None = None


def attenuate(parent: Ticket, *, subject: str, extra: tuple[Caveat, ...] = ()) -> Ticket:
    return Ticket(
        intent_id=parent.intent_id,
        subject=subject,
        caveats=_merge(parent.caveats, extra),
        parent=parent,
    )


def _merge(base: tuple[Caveat, ...], extra: tuple[Caveat, ...]) -> tuple[Caveat, ...]:
    by_kind = {c.kind: c.value for c in base}
    for c in extra:
        if c.kind not in by_kind:
            by_kind[c.kind] = c.value
        elif c.kind == "calls":
            by_kind[c.kind] = str(min(int(by_kind[c.kind]), int(c.value)))
        elif c.kind == "until":
            by_kind[c.kind] = min(by_kind[c.kind], c.value)
        else:
            items = by_kind[c.kind].split(",")
            if c.value not in items:
                items.append(c.value)
            by_kind[c.kind] = ",".join(items)
    return tuple(Caveat(kind=k, value=v) for k, v in by_kind.items())


def verify_chain(ticket: Ticket) -> bool:
    node = ticket
    while node.parent is not None:
        if not _at_least_as_strict(parent=node.parent.caveats, child=node.caveats):
            return False
        node = node.parent
    return True


def _at_least_as_strict(*, parent: tuple[Caveat, ...], child: tuple[Caveat, ...]) -> bool:
    child_by_kind = {c.kind: c.value for c in child}
    for c in parent:
        if c.kind not in child_by_kind:
            return False
        if c.kind in _LIST_KINDS:
            parent_items = set(c.value.split(","))
            child_items = set(child_by_kind[c.kind].split(","))
            if not parent_items <= child_items:
                return False
        elif c.kind == "calls":
            if int(child_by_kind[c.kind]) > int(c.value):
                return False
        elif c.kind == "until":
            if datetime.fromisoformat(child_by_kind[c.kind]) > datetime.fromisoformat(c.value):
                return False
    return True
