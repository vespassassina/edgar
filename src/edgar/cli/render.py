"""What reaches the terminal [CLI-5, CLI-15, CLI-21, CLI-23].

Text streams a line at a time, wrapped to the terminal's width. A whole line is
what a terminal-native REPL can print above its prompt without breaking it, and it
stays in the terminal's own scrollback: no alternate screen, nothing redrawn but
the status line. Markdown is left as written; rendering it would mean redrawing
text already printed.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from edgar.core.events import (
    AsideFinished,
    Event,
    ModelSelected,
    ProviderRetry,
    ReasoningDropped,
    RequestFinished,
    SteerApplied,
    TextDelta,
    ThinkingDelta,
    ToolCallRepaired,
    ToolFinished,
    ToolProposed,
    TurnFinished,
)


class Printer:
    def __init__(
        self, write: Callable[[str], None], *, color: bool, width: Callable[[], int]
    ) -> None:
        self._write, self.color, self._width = write, color, width
        self._line, self._dim = "", False
        self._held: list[str] = []  # blocks waiting for the end of the current line

    def text(self, delta: str, *, dim: bool = False) -> None:
        if dim != self._dim:
            self.end()
            self._dim = dim
        self._line += delta
        width = max(20, self._width() - 1)
        while True:
            head = self._line.split("\n", 1)[0]
            if len(head) > width:  # wrap at the last space that fits
                cut = head.rfind(" ", 0, width)
                cut = width if cut <= 0 else cut
                self._out(head[:cut])
                self._line = self._line[cut:].lstrip(" ")
            elif "\n" in self._line:
                self._out(head)
                self._line = self._line[len(head) + 1 :]
            else:
                break
        if not self._line:
            self._release()

    def end(self) -> None:
        """Close the current line, then print whatever was held for it."""
        if self._line:
            self._out(self._line)
            self._line = ""
        self._release()

    def block(self, text: str, *, dim: bool = False) -> None:
        """A block of its own, printed at the next line boundary, never mid-line."""
        styled = "\n".join(self._style(line, dim) for line in text.split("\n"))
        if self._line:
            self._held.append(styled)
        else:
            self._write(styled + "\n")

    def clear(self) -> None:
        self._write("\x1b[2J\x1b[H")

    def _out(self, line: str) -> None:
        self._write(self._style(line, self._dim) + "\n")

    def _style(self, line: str, dim: bool) -> str:
        return f"\x1b[2m{line}\x1b[0m" if dim and self.color and line else line

    def _release(self) -> None:
        held, self._held = self._held, []
        for text in held:
            self._write(text + "\n")


class Renderer:
    """The interactive transcript: text, tool activity and notices, from events."""

    def __init__(self, printer: Printer, *, show_thinking: bool = False) -> None:
        self.printer = printer
        self.show_thinking = show_thinking

    def __call__(self, event: Event) -> None:
        p = self.printer
        if event.depth:  # subagents render in their own rows (v1)
            return
        if isinstance(event, TextDelta):
            p.text(event.text)
        elif isinstance(event, ThinkingDelta):
            if self.show_thinking:
                p.text(event.text, dim=True)
        elif isinstance(event, ToolProposed):
            p.end()
            p.block(f"· {event.tool} {event.args_preview}", dim=True)
        elif isinstance(event, ToolFinished) and not event.ok:
            p.block("  ✗ failed; the error went back to the model", dim=True)
        elif isinstance(event, RequestFinished | TurnFinished):
            p.end()
            if isinstance(event, TurnFinished) and event.reason == "cancelled":
                p.block("cancelled", dim=True)
        elif isinstance(event, AsideFinished):
            p.block(f"── btw ──\n{event.answer.strip()}\n────────")
        else:
            notice = _notice(event)
            if notice:
                p.block(notice, dim=True)


def _notice(event: Event) -> str | None:
    if isinstance(event, SteerApplied):
        return f"↪ steered: {event.text}"
    if isinstance(event, ProviderRetry):
        return f"{event.reason}; retrying in {event.after_s:.1f} s"
    if isinstance(event, ReasoningDropped):
        return f"reasoning from {event.from_origin} not sent to {event.to_family}"
    if isinstance(event, ToolCallRepaired):
        return f"repaired a {event.tool} call ({event.repair})"
    if isinstance(event, ModelSelected):
        return f"model: {event.model} ({event.reason})"
    return None


def event_line(event: Event) -> str:
    """One line of `--events`: JSON, one event per line [CLI-18]."""
    return json.dumps(event.to_dict(), ensure_ascii=False, default=str)
