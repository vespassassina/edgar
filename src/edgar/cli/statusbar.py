"""The status line, rebuilt from events alone [CLI-5, CLI-6, CLI-8].

In the REPL it is the prompt's bottom toolbar; with `-p` it is one line on stderr,
redrawn about ten times a second and only when stderr is a terminal. Either way
it is the only thing on screen that is ever redrawn [CLI-23].
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from collections.abc import Callable
from typing import TextIO

from edgar.core.events import (
    AsideFinished,
    Event,
    InputQueued,
    Paused,
    RequestFinished,
    RequestStarted,
    Resumed,
    TextDelta,
    ThinkingDelta,
    ToolStarted,
    TurnFinished,
    TurnStarted,
)

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Status:
    def __init__(self, model: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.model, self.clock = model, clock
        self.phase = ""  # empty between turns
        self.tools = 0
        self.context = 0  # tokens in the last request
        self.cost: float | None = 0.0  # this session; None once a price is unknown
        self.queued = 0
        self.paused = False
        self.started = 0.0

    def __call__(self, event: Event) -> None:
        if event.depth:
            return
        if isinstance(event, TurnStarted):
            self.phase, self.tools, self.started = "thinking", 0, self.clock()
            self.model = event.model
        elif isinstance(event, RequestStarted):
            self.phase, self.context = "thinking", event.input_tokens
        elif isinstance(event, TextDelta | ThinkingDelta):
            self.phase = "writing" if isinstance(event, TextDelta) else "thinking"
        elif isinstance(event, ToolStarted):
            self.phase, self.tools = event.tool, self.tools + 1
        elif isinstance(event, RequestFinished | AsideFinished):
            if isinstance(event, RequestFinished):  # an aside is not in the context
                self.context = event.usage.input_tokens + event.usage.output_tokens
            self.cost = None if self.cost is None or event.cost is None else self.cost + event.cost
        elif isinstance(event, TurnFinished):
            self.phase = ""
        elif isinstance(event, InputQueued):
            self.queued = event.position
        elif isinstance(event, Paused | Resumed):
            self.paused = isinstance(event, Paused)

    def line(self) -> str:
        parts = [self.model, f"{self.context / 1000:.1f}k tok", _money(self.cost)]
        if self.queued:
            parts.append(f"{self.queued} queued")
        if self.paused:
            parts.append("paused")
        if not self.phase:
            return " · ".join(parts)
        elapsed = self.clock() - self.started
        frame = FRAMES[int(elapsed * 10) % len(FRAMES)]
        tools = f"{self.tools} tool{'s' * (self.tools != 1)}"
        return " · ".join([f"{frame} {self.phase}", tools, *parts[1:], f"{elapsed:.0f}s"])


def _money(cost: float | None) -> str:
    return "cost unknown" if cost is None else f"${cost:.3f}"


class StderrLine:
    """The `-p` status line: one line on stderr, cleared before the result prints."""

    def __init__(self, status: Status, stream: TextIO | None = None) -> None:
        self.status, self.stream = status, stream or sys.stderr

    async def run(self) -> None:
        while True:
            width = shutil.get_terminal_size().columns
            self.stream.write("\r\x1b[2K" + self.status.line()[: width - 1])
            self.stream.flush()
            await asyncio.sleep(0.1)

    def clear(self) -> None:
        self.stream.write("\r\x1b[2K")
        self.stream.flush()


def terminal_ready(stream: TextIO) -> bool:
    """A terminal that understands escape sequences. On Windows the console must be
    switched to VT mode first; when that fails, no status line rather than raw
    escapes [NFR-6]."""
    if not stream.isatty():
        return False
    if sys.platform != "win32":
        return True
    import ctypes  # Windows only; never imported elsewhere

    kernel = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]  # Windows only
    handle = kernel.GetStdHandle(-12)  # STD_ERROR_HANDLE
    mode = ctypes.c_uint32()
    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))  # VT processing
