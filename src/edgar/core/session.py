"""Session state. In memory for now; JSONL persistence arrives in M5 [ADR-0010]."""

from __future__ import annotations

import asyncio
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
    title: str | None = None  # first line of the first prompt; never a model call [CLI-28]
    _resumed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def __post_init__(self) -> None:
        self._resumed.set()

    @property
    def paused(self) -> bool:
        return not self._resumed.is_set()

    def pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._resumed.set()

    async def wait_if_paused(self) -> None:
        """The loop waits here, at the safe point: what is in flight finishes first,
        nothing is cancelled [CLI-27]."""
        await self._resumed.wait()

    @property
    def dir(self) -> Path:
        return self.cwd / ".edgar" / "sessions" / self.id

    def append(self, message: Message) -> None:
        if self.title is None and message.role == "user":
            self.title = message.text.strip().split("\n", 1)[0][:60] or None
        self.transcript.append(message)

    def steer(self, text: str) -> None:
        self.pending_steers.append(text)

    def steers_pending(self) -> bool:
        return bool(self.pending_steers)

    def take_back_steers(self) -> list[str]:
        """Undelivered steers, returned to the input line after a cancel [CLI-13]."""
        taken, self.pending_steers = self.pending_steers, []
        return taken

    def drain_steers(self) -> list[str]:
        """Append pending steers as user messages. Called only between units [CLI-13]."""
        drained, self.pending_steers = self.pending_steers, []
        for text in drained:
            self.append(Message.user(text, via="steer"))
        return drained
