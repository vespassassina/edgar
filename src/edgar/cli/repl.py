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
from edgar.cli import trust
from edgar.cli.render import Printer, Renderer
from edgar.cli.setup import (
    Setup,
    authorise_verify,
    begin,
    daily,
    finish,
    prepare,
    runtime,
    setup,
    verify_for_turn,
)
from edgar.cli.statusbar import Status
from edgar.core import aside
from edgar.core.errors import EdgarError
from edgar.core.events import Event, EventBus, FactProposed, FactSaved, InputQueued
from edgar.core.loop import Runtime, run_turn
from edgar.core.session import Session
from edgar.permissions.guard import Answer
from edgar.providers.routing import Selection
from edgar.skills.activate import bodies, matching, touched_paths
from edgar.tools.mcp.client import close

Ask = Callable[[str], Awaitable[str]]


class Shell:
    def __init__(
        self,
        *,
        setup: Setup,
        session: Session,
        rt: Runtime,
        renderer: Renderer,
        status: Status,
        ask: Ask,
    ) -> None:
        self.setup, self.config = setup, setup.config
        self.session, self.rt = session, rt
        self.renderer, self.printer, self.status = renderer, renderer.printer, status
        self.ask = ask
        self.queue: deque[str] = deque()
        self.turn: asyncio.Task[None] | None = None
        self.asides: set[asyncio.Task[None]] = set()
        self.pending_input = ""  # put back on the input line after a cancel
        self.question: asyncio.Future[str] | None = None  # the next line answers it
        self.asking = ""  # the prompt shown while a question waits
        self.proposed: list[FactProposed] = []  # the model's facts, asked about at turn end
        self.done = False
        status.cost = session.cost
        rt.bus.subscribe(self._record)

    def _record(self, event: Event) -> None:
        if isinstance(event, FactProposed):
            self.proposed.append(event)
        if self.session.log is not None:
            self.session.log.event(event)  # the audit trail and turn costs [PERM-10]

    def open(self, session: Session) -> None:
        """`/new`, `/clear`, `/load`: the current session ends, and stays on disk."""
        finish(self.setup, self.session, self.rt.bus)
        self.session, self.status.cost, self.status.context = session, session.cost, 0
        if session.model != self.rt.name:
            self.switch(session.model)

    def prompt_text(self) -> str:
        return self.asking if self.question else "> "

    async def _question(self, prompt: str) -> str:
        # Asked from inside a turn; answered by the next line typed. One question at a
        # time, through the one prompt [PERM-6, TOOL-12].
        self.asking, self.question = prompt, asyncio.get_running_loop().create_future()
        try:
            return (await self.question).strip().lower()[:1]
        finally:
            self.question = None

    async def permission(self, tool: str, subject: str, reason: str) -> Answer:
        self.say(f"{tool} wants {subject}\n  ({reason})")
        answer = await self._question("allow? [y]es once, [s]ession, [a]lways, [n]o > ")
        return {"y": "once", "s": "session", "a": "always"}.get(answer, "deny")  # type: ignore[return-value]  # the Answer literals

    async def confirm_facts(self) -> None:
        """What the model proposed with `remember` is saved only on a typed yes; no, or
        just Enter, forgets it, and it is never in a prompt [MEM-21]."""
        proposed, self.proposed = self.proposed, []
        if not proposed:
            return
        noun = "fact" if len(proposed) == 1 else "facts"
        self.say(
            f"{len(proposed)} {noun} proposed:\n" + "\n".join(f'  "{p.text}"' for p in proposed)
        )
        ids = [p.fact_id for p in proposed]
        if await self._question("save? [y/N] > ") != "y":
            for fact in ids:
                self.setup.memory.forget(fact)
            self.say("not saved")
            return
        self.setup.memory.confirm(ids)
        for fact in ids:
            self.rt.bus.emit(FactSaved(fact_id=fact, provenance="model-proposed"))
        self.say("saved; in the prompt from the next session")

    @property
    def busy(self) -> bool:
        return self.turn is not None and not self.turn.done()

    def say(self, text: str) -> None:
        self.printer.block(text)

    async def handle(self, line: str) -> None:
        if self.question is not None and not self.question.done():
            self.question.set_result(line)  # the line answers the pending question
            return
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
            touched = touched_paths(self.session.transcript)
            hits = matching(self.setup.skills, text, touched)
            rt = verify_for_turn(self.setup, self.rt, hits)
            await authorise_verify(rt, self.session)
            rt = daily(self.setup, rt)
            result = await run_turn(self.session, text, rt, attached=bodies(hits))
            if result.reason == "verification_failed":  # [VER-5]
                self.say(
                    f"⚠ the check `{self.rt.verify.command if self.rt.verify else ''}` "
                    "still fails after its last attempt; the session goes on"
                )
            elif result.reason == "budget_exceeded":  # [BUD-3]
                self.say("⚠ a cost cap was reached; the turn stopped. See [budget] and /cost")
            await self.confirm_facts()
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
        self.rt = runtime(self.setup, self.rt.bus, choice=choice)
        self.session.model = self.status.model = model
        self.session.record({"type": "model", "model": model})

    async def close(self) -> None:
        if self.question and not self.question.done():
            self.question.set_result("n")
        self.stop()
        running = [t for t in (self.turn, *self.asides) if t is not None and not t.done()]
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        await close(self.setup.servers)  # the MCP servers this session started
        finish(self.setup, self.session, self.rt.bus)


async def interact(
    *,
    cwd: Path | None,
    model: str | None,
    mode: str | None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    show_thinking: bool = False,
    color: bool = True,
    verify: str | None = None,
    project_exec: bool = True,
    resume: str | None = None,
) -> int:
    # The interactive path's own dependency, loaded only here (NFR-1).
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.output import ColorDepth
    from prompt_toolkit.patch_stdout import patch_stdout

    root, config = prepare(cwd, model=model, mode=mode, env=env, home=home, confirm_yolo=_yolo)
    home = home or Path.home()
    if project_exec and not trust.trusted(root, config, home):  # [PERM-13]
        print(trust.describe(root, config))
        project_exec = input("trust this project and let it run? [y/N] ").strip().lower() == "y"
        if project_exec:
            trust.trust(root, config, home)
    status = Status("")
    history = home / ".edgar" / "history"
    history.parent.mkdir(parents=True, exist_ok=True)
    prompt: PromptSession[str] = PromptSession(
        history=FileHistory(str(history)),
        bottom_toolbar=lambda: "\n".join(" " + row for row in status.rows()),
        refresh_interval=0.1,
        color_depth=None if color else ColorDepth.MONOCHROME,
    )

    async def ask(question: str) -> str:
        return await prompt.prompt_async(question)

    shell_ref: list[Shell] = []

    async def permission(tool: str, subject: str, reason: str) -> Answer:
        return await shell_ref[0].permission(tool, subject, reason)

    s = setup(
        root, config, home=home, env=env, verify=verify, project_exec=project_exec, asker=permission
    )
    for warning in s.warnings:
        print(f"edgar: {warning}")

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
            s.config = replace(config, model=replace(config.model, default=chosen))
        session, rt = begin(s, bus, resume)
        status.model = rt.name
        shell = Shell(setup=s, session=session, rt=rt, renderer=renderer, status=status, ask=ask)
        shell_ref.append(shell)
        if resume is not None:  # the conversation as it was left [CLI-11]
            renderer.show(session.transcript)
        printer.block(f"edgar {__version__} · {rt.name} · {session.mode} · /help", dim=True)
        await _read(shell, prompt.prompt_async)
    return 0


async def _read(shell: Shell, read: Callable[..., Awaitable[str]]) -> None:
    last_interrupt = 0.0
    while not shell.done:
        default, shell.pending_input = shell.pending_input, ""
        try:
            line = await read(shell.prompt_text, default=default)
        except KeyboardInterrupt:
            if shell.question is not None:
                shell.question.set_result("n")  # Ctrl-C at a question means no
                continue
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


def _yolo() -> bool:
    """A typed confirmation, never a keypress: yolo turns off every check [PERM-9]."""
    return input("yolo turns off every permission check. Type yolo to confirm: ") == "yolo"


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def color_wanted(flag_off: bool) -> bool:
    return not flag_off and "NO_COLOR" not in os.environ  # [CLI-15]
