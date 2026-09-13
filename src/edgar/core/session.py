"""Session state. In memory for now; JSONL persistence arrives in M5 [ADR-0010]."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from edgar.core.message import Message

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id() -> str:
    """A ULID: 48 bits of milliseconds then 80 random bits, sortable by creation time."""
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(os.urandom(10))
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


@dataclass
class Session:
    cwd: Path  # launch dir [CLI-16]
    model: str
    mode: str
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    transcript: list[Message] = field(default_factory=list)
    depth: int = 0
    parent_id: str | None = None
    pending_steers: list[str] = field(default_factory=list)  # drained at the safe point

    @property
    def dir(self) -> Path:
        return self.cwd / ".edgar" / "sessions" / self.id

    def append(self, message: Message) -> None:
        self.transcript.append(message)

    def steer(self, text: str) -> None:
        self.pending_steers.append(text)

    def steers_pending(self) -> bool:
        return bool(self.pending_steers)

    def drain_steers(self) -> list[str]:
        """Append pending steers as user messages. Called only between units [CLI-13]."""
        drained, self.pending_steers = self.pending_steers, []
        for text in drained:
            self.append(Message.user(text, via="steer"))
        return drained
