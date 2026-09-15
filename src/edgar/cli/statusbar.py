"""The status line, rebuilt from events alone [CLI-5, CLI-6, CLI-8].

In the REPL it is the prompt's bottom toolbar; with `-p` it is a block of lines
on stderr, redrawn about ten times a second and only when stderr is a terminal.
One subagent running alongside the main turn gets its own row, appearing when it
starts and gone once it finishes, so concurrent subagents never interleave into
one confusing stream [SUB-9]. Either way this is the only thing ever redrawn
[CLI-23].
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO

from edgar.core.events import (
    AsideFinished,
    Compacted,
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


@dataclass
class _Row:
    """A subagent's own phase, tool count and start time, kept only while it
    runs; `Status.__call__` drops the entry on its `TurnFinished` [SUB-9]."""

    phase: str = "thinking"
    tools: int = 0
    started: float = 0.0


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
        self.agents: dict[str, _Row] = {}  # subagents running now, insertion order [SUB-9]

    def __call__(self, event: Event) -> None:
        if event.depth:
            self._subagent(event)
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
        elif isinstance(event, RequestFinished | AsideFinished | Compacted):
            if isinstance(event, RequestFinished):  # an aside is not in the context
                self.context = event.usage.input_tokens + event.usage.output_tokens
            elif isinstance(event, Compacted):
                self.context = event.after
            self.cost = None if self.cost is None or event.cost is None else self.cost + event.cost
        elif isinstance(event, TurnFinished):
            self.phase = ""
        elif isinstance(event, InputQueued):
            self.queued = event.position
        elif isinstance(event, Paused | Resumed):
            self.paused = isinstance(event, Paused)

    def _subagent(self, event: Event) -> None:
        # A row per running agent_id; consecutive `task` calls fan out [TOOL-12],
        # so more than one of these can exist at once.
        if isinstance(event, TurnFinished):
            self.agents.pop(event.agent_id, None)
            return
        row = self.agents.setdefault(event.agent_id, _Row(started=self.clock()))
        if isinstance(event, TurnStarted):
            row.phase, row.tools, row.started = "thinking", 0, self.clock()
        elif isinstance(event, RequestStarted):
            row.phase = "thinking"
        elif isinstance(event, TextDelta | ThinkingDelta):
            row.phase = "writing" if isinstance(event, TextDelta) else "thinking"
        elif isinstance(event, ToolStarted):
            row.phase, row.tools = event.tool, row.tools + 1

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

    def rows(self) -> list[str]:
        """The main line, then one row per subagent running right now [SUB-9]."""
        return [self.line(), *(self._agent_line(i, r) for i, r in self.agents.items())]

    def _agent_line(self, agent_id: str, row: _Row) -> str:
        elapsed = self.clock() - row.started
        frame = FRAMES[int(elapsed * 10) % len(FRAMES)]
        tools = f"{row.tools} tool{'s' * (row.tools != 1)}"
        return f"  {frame} {agent_id}: {row.phase} · {tools} · {elapsed:.0f}s"


def _money(cost: float | None) -> str:
    return "cost unknown" if cost is None else f"${cost:.3f}"


class StderrLine:
    """The `-p` status block: one row per running agent on stderr, redrawn in
    place and cleared before the result prints."""

    def __init__(self, status: Status, stream: TextIO | None = None) -> None:
        self.status, self.stream = status, stream or sys.stderr
        self._drawn = 0  # how many rows the last redraw left on screen [SUB-9]

    async def run(self) -> None:
        while True:
            self._draw()
            await asyncio.sleep(0.1)

    def _draw(self) -> None:
        width = shutil.get_terminal_size().columns
        rows = self.status.rows()
        if self._drawn > 1:  # back to the top-left of the block we drew last time
            self.stream.write(f"\x1b[{self._drawn - 1}A")
        for i, row in enumerate(rows):
            self.stream.write("\r\x1b[2K" + row[: width - 1])
            if i < len(rows) - 1:
                self.stream.write("\n")
        self.stream.write("\x1b[J")  # a shrunk block leaves nothing stale below it
        self.stream.flush()
        self._drawn = len(rows)

    def clear(self) -> None:
        if self._drawn > 1:
            self.stream.write(f"\x1b[{self._drawn - 1}A")
        self.stream.write("\r\x1b[2K\x1b[J")
        self.stream.flush()
        self._drawn = 0


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
