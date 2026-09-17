"""Facts templated from ErrorRecords, saved only after repeats [MEM-22]."""

# This file reads one field of one event: ToolFinished.error, the record the tool
# pipeline computed from what it did itself. The failure's own text is in the
# ToolResultBlock and never reaches the bus, so there is nothing here that an
# attacker who controls a tool's output could have written, except a program
# name, which is a basename restricted to [A-Za-z0-9._-] and sanitised again
# below [ADR-0017].
#
# Per failure, in order:
#   1. the kind must be one worth keeping; a rejected call or a cancelled turn
#      says something about the model or the user, not about the project
#   2. count this sighting against the project's scope
#   3. at REPEATS, fill a template with the four fields and save one fact
#   4. mark it saved, so the same failure never files a second fact
#
# REPEATS is 3. Twice is a model retrying the same command inside one turn, which
# happens constantly; three times across a project is the project telling you
# something. The fact goes in at the store's low confidence for anything not
# hand-typed, which is what "active at low confidence" means in ADR-0017.

from __future__ import annotations

import re

from edgar.core.events import Event, EventBus, FactProposed, FactSaved, ToolFinished
from edgar.core.message import ErrorRecord
from edgar.learning.experience import Experience
from edgar.memory.store import Memory

REPEATS = 3
UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# One template per kind worth learning. `validation` and `cancelled` are left out
# on purpose: the first is the model's mistake, the second is the user's choice.
# `provider_http` is about the provider, not about this project.
TEMPLATES = {
    "not_found": "{what} was not found {where}in this project ({times} times)",
    "nonzero_exit": "{what} exits {code} in this project ({times} times)",
    "timeout": "{what} times out in this project ({times} times)",
    "permission_denied": "{what} is not permitted in this project ({times} times)",
    "internal": "{what} fails with an internal error in this project ({times} times)",
}


def key(record: ErrorRecord) -> str:
    """What counts as the same failure happening again."""
    code = "" if record.exit_code is None else str(record.exit_code)
    return f"{record.tool}|{record.kind}|{record.program or ''}|{code}"


def template(record: ErrorRecord, times: int) -> str | None:
    """The fact's text, built only from the record's four fields [MEM-22]."""
    if record.kind not in TEMPLATES:
        return None
    # A command that failed is named by its program; anything else by its tool.
    if record.program:
        what = f"`{UNSAFE.sub('', record.program)}`"
        where = "on PATH " if record.kind == "not_found" else ""
    else:
        what = f"the `{UNSAFE.sub('', record.tool)}` tool"
        where = ""
    return TEMPLATES[record.kind].format(what=what, where=where, times=times, code=record.exit_code)


class ErrorFacts:
    """The subscriber. A subagent's failures count too: they happen in the same
    project, and the record is the same shape whoever ran the tool."""

    def __init__(self, store: Experience, memory: Memory, *, scope: str, bus: EventBus) -> None:
        self.store, self.memory, self.scope, self.bus = store, memory, scope, bus

    def __call__(self, event: Event) -> None:
        # 1. One event, one field, and only the kinds worth keeping.
        if not isinstance(event, ToolFinished) or event.error is None:
            return
        record = event.error
        if record.kind not in TEMPLATES:
            return
        # 2. Count it, and stop unless this sighting is the one that earns a fact.
        seen, saved = self.store.seen(self.scope, key(record), _fields(record))
        if saved or seen < REPEATS:
            return
        text = template(record, seen)
        if text is None:
            return
        # 3. Save once, and say so: nothing enters memory without being shown.
        fact = self.memory.add(text, self.scope, provenance="error-template")
        self.store.mark_saved(self.scope, key(record))
        if fact.status == "active":
            self.bus.emit(FactSaved(fact_id=fact.id, provenance=fact.provenance, text=fact.text))
        else:
            self.bus.emit(FactProposed(fact_id=fact.id, text=fact.text))


def _fields(record: ErrorRecord) -> dict[str, object]:
    # What the errors table stores: the record, and nothing derived from text.
    return {
        "tool": record.tool,
        "kind": record.kind,
        "program": record.program,
        "exit_code": record.exit_code,
    }
