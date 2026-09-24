# 1. The key: 32 random bytes at ~/.edgar/receipt.key, made once, 0600 from its first byte, never
#    read by anything the model can reach -- `permissions.matcher.CREDENTIALS`
#    lists it so the hard layer refuses it outright [ADR-0039].
# 2. Each line is {"prev", "kind", "data", "hmac"}. `prev` is the SHA-256 of
#    the previous line's exact text (the genesis line points at 64 zeros);
#    `hmac` signs this line's own prev+kind+data. Tampering with an earlier
#    line breaks every hash after it; tampering with a line's own content
#    breaks its own signature. verify() checks both, in order, and stops at
#    the first break.
# 3. Receipts is the bus subscriber: one line per intent, ticket, delegation,
#    refusal, and permission decision -- the same "the boundary is the
#    subscription" shape as broker/intent.py's Intents.

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from edgar.broker.ticket import Ticket
from edgar.core.events import Event, PermissionResolved, PromptTyped, ScopeRefused, TurnStarted

GENESIS = "0" * 64


def key_path(home: Path) -> Path:
    return home / ".edgar" / "receipt.key"


def load_or_create_key(home: Path) -> bytes:
    path = key_path(home)
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    # Created 0600 in one call, never written wider and narrowed after. On
    # Windows the mode is ignored and the user profile's ACL guards the file.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


def _canonical(prev: str, kind: str, data: dict[str, Any]) -> str:
    body = {"prev": prev, "kind": kind, "data": data}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def sign(key: bytes, prev: str, kind: str, data: dict[str, Any]) -> str:
    return hmac_lib.new(key, _canonical(prev, kind, data).encode(), hashlib.sha256).hexdigest()


def append(path: Path, key: bytes, prev: str, kind: str, data: dict[str, Any]) -> str:
    """Writes one signed line; returns its own hash, the next line's `prev`."""
    line = {"prev": prev, "kind": kind, "data": data, "hmac": sign(key, prev, kind, data)}
    text = json.dumps(line, sort_keys=True, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Break:
    line: int
    reason: str


def verify(path: Path, key: bytes) -> Break | None:
    """Replays the whole chain; `None` means every line still holds [CAP-9]."""
    prev = GENESIS
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        entry = json.loads(raw)
        if entry["prev"] != prev:
            return Break(n, "the hash chain breaks here")
        expected = sign(key, entry["prev"], entry["kind"], entry["data"])
        if not hmac_lib.compare_digest(expected, entry["hmac"]):
            return Break(n, "the signature does not match")
        prev = hashlib.sha256(raw.encode()).hexdigest()
    return None


@dataclass(slots=True)
class Receipts:
    path: Path
    key: bytes
    prev: str = GENESIS

    def record(self, kind: str, data: dict[str, Any]) -> None:
        self.prev = append(self.path, self.key, self.prev, kind, data)

    def record_ticket(self, ticket: Ticket) -> None:
        self.record(
            "ticket", {"subject": ticket.subject, "caveats": [asdict(c) for c in ticket.caveats]}
        )

    def __call__(self, event: Event) -> None:
        if isinstance(event, PromptTyped) and event.depth == 0:
            self.record("intent", {"text": event.text})
        elif isinstance(event, TurnStarted) and event.depth > 0:
            self.record("delegate", {"agent": event.agent_id, "depth": event.depth})
        elif isinstance(event, ScopeRefused):
            self.record(
                "refuse", {"tool": event.tool, "caveat": event.caveat, "reason": event.reason}
            )
        elif isinstance(event, PermissionResolved):
            self.record(
                "permission",
                {"tool": event.tool, "decision": event.decision, "subject": event.subject},
            )
