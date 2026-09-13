"""The interactive REPL [CLI-1, CLI-12, CLI-13, CLI-23, CLI-24, CLI-27].

`Shell` is the REPL without a terminal: what each typed line does. Tests drive it
directly. `interact()` connects it to prompt_toolkit, which keeps a prompt at the
bottom of the screen while a turn runs, so input is never blocked: plain text
queues, `/steer` reaches the turn at its next safe point, `/btw` asks on the side.
The status line is the prompt's bottom toolbar; everything else prints above the
prompt and stays in the terminal's scrollback.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path

from edgar import __version__
from edgar.cli.render import Printer, Renderer
from edgar.cli.setup import prepare, runtime
from edgar.cli.statusbar import Status
from edgar.config.schema import Config
from edgar.core import aside
from edgar.core.errors import EdgarError
from edgar.core.events import EventBus, InputQueued
from edgar.core.loop import Runtime, run_turn
from edgar.core.session import Session
from edgar.providers.routing import Selection

Ask = Callable[[str], Awaitable[str]]


class Shell:
    def __init__(
        self,
        *,
        config: Config,
        root: Path,
        env: Mapping[str, str] | None,
        session: Session,
        rt: Runtime,
        renderer: Renderer,
        status: Status,
        ask: Ask,
    ) -> None:
        self.config, self.root, self.env = config, root, env
        self.session, self.rt = session, rt
        self.renderer, self.printer, self.status = renderer, renderer.printer, status
        self.ask = ask
        self.queue: deque[str] = deque()
        self.turn: asyncio.Task[None] | None = None
        self.asides: set[asyncio.Task[None]] = set()
        self.pending_input = ""  # put back on the input line after a cancel
        self.done = False

    @property
    def busy(self) -> bool:
        return self.turn is not None and not self.turn.done()

    def say(self, text: str) -> None:
        self.printer.block(text)

    async def handle(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        if text.startswith("/"):
            from edgar.cli.slash import dispatch

            await dispatch(self, text)
        else:
            self.submit(text)

    def submit(self, text: str) -> None:
        """Run now, or queue behind the turn in progress [CLI-13]."""
        if not self.busy:
            self.turn = asyncio.create_task(self._run(text))
            return
        self.queue.append(text)
        self.status.queued = len(self.queue)
        self.rt.bus.emit(InputQueued(text=text, position=len(self.queue)))

    async def _run(self, text: str) -> None:
        try:
            await run_turn(self.session, text, self.rt)
        except asyncio.CancelledError:
            return  # the loop sealed the transcript; nothing queued runs after a cancel
        except EdgarError as exc:
            self.say(f"edgar: {exc}" + (f"\nhint: {exc.hint}" if exc.hint else ""))
        if self.queue:
            following = self.queue.popleft()
            self.status.queued = len(self.queue)
            self.turn = asyncio.create_task(self._run(following))

    def stop(self) -> str:
        """Cancel the turn, like one Ctrl-C. Queued and undelivered steered text comes
        back, to go on the input line unsent [CLI-12, CLI-13]."""
        back = [*self.queue, *self.session.take_back_steers()]
        self.queue.clear()
        self.status.queued = 0
        self.session.resume()
        if self.turn is not None and self.busy:
            self.turn.cancel()
        return "\n".join(back)

    def ask_aside(self, question: str) -> None:
        task = asyncio.create_task(self._aside(question))
        self.asides.add(task)
        task.add_done_callback(self.asides.discard)

    async def _aside(self, question: str) -> None:
        try:
            await aside.ask(self.session, question, self.rt)
        except EdgarError as exc:
            self.say(f"edgar: {exc}")

    def switch(self, model: str) -> None:
        """`/model NAME`: the rest of the session runs on `model` [CLI-28]."""
        choice = Selection(model, "user", "/model")
        self.rt = runtime(self.config, self.root, self.rt.bus, env=self.env, choice=choice)
        self.session.model = self.status.model = model

    async def close(self) -> None:
        self.stop()
        running = [t for t in (self.turn, *self.asides) if t is not None and not t.done()]
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)


async def interact(
    *,
    cwd: Path | None,
    model: str | None,
    mode: str | None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    show_thinking: bool = False,
    color: bool = True,
) -> int:
    # The interactive path's own dependency, loaded only here (NFR-1).
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.output import ColorDepth
    from prompt_toolkit.patch_stdout import patch_stdout

    root, config = prepare(cwd, model=model, mode=mode, env=env, home=home)
    status = Status("")
    history = (home or Path.home()) / ".edgar" / "history"
    history.parent.mkdir(parents=True, exist_ok=True)
    prompt: PromptSession[str] = PromptSession(
        history=FileHistory(str(history)),
        bottom_toolbar=lambda: " " + status.line(),
        refresh_interval=0.1,
        color_depth=None if color else ColorDepth.MONOCHROME,
    )

    async def ask(question: str) -> str:
        return await prompt.prompt_async(question)

    with patch_stdout(raw=True):
        printer = Printer(_write, color=color, width=lambda: shutil.get_terminal_size().columns)
        renderer = Renderer(printer, show_thinking=show_thinking)
        bus = EventBus()
        bus.subscribe(renderer)
        bus.subscribe(status)
        if config.model.default is None:
            from edgar.cli.models import pick

            printer.block("No model configured yet. Pick one:")
            chosen = await pick(config, env, ask, printer.block)
            if chosen is None:
                return 3
            config = replace(config, model=replace(config.model, default=chosen))
        rt = runtime(config, root, bus, env=env)
        status.model = rt.name
        session = Session(cwd=root, model=rt.name, mode=config.permissions.mode)
        shell = Shell(
            config=config,
            root=root,
            env=env,
            session=session,
            rt=rt,
            renderer=renderer,
            status=status,
            ask=ask,
        )
        printer.block(f"edgar {__version__} · {rt.name} · {session.mode} · /help", dim=True)
        await _read(shell, prompt.prompt_async)
    return 0


async def _read(shell: Shell, read: Callable[..., Awaitable[str]]) -> None:
    last_interrupt = 0.0
    while not shell.done:
        default, shell.pending_input = shell.pending_input, ""
        try:
            line = await read("> ", default=default)
        except KeyboardInterrupt:
            now = time.monotonic()
            if shell.busy or shell.queue:
                shell.pending_input = shell.stop()  # once: cancel the turn [CLI-12]
            elif now - last_interrupt < 2:
                break  # twice: exit
            else:
                shell.say("Ctrl-C again to exit, or /quit")
            last_interrupt = now
            continue
        except EOFError:
            break
        await shell.handle(line)
    await shell.close()


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def color_wanted(flag_off: bool) -> bool:
    return not flag_off and "NO_COLOR" not in os.environ  # [CLI-15]
