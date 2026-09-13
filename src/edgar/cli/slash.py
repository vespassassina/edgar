"""Slash commands [CLI-14, CLI-27, CLI-28].

Each command is a small function over the `Shell`. Commands whose machinery lands
in a later milestone say which one, rather than pretending to work.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import get_args

from edgar.cli.repl import Shell
from edgar.config.schema import Mode
from edgar.core.errors import EdgarError
from edgar.core.events import Paused, Resumed
from edgar.core.session import Session

Command = Callable[[Shell, str], Awaitable[None]]
COMMANDS: dict[str, tuple[Command, str]] = {}

LATER = {
    "M8": "/browser",
    "M5": "/compact /plan /go /reset /history /undo /retry /sessions /load /save",
    "M6": "/skills /tools",
    "v1": "/fork /remember /memory /agents /init",
}


def command(names: str, help: str) -> Callable[[Command], Command]:
    def register(fn: Command) -> Command:
        for name in names.split():
            COMMANDS[name] = (fn, help)
        return fn

    return register


async def dispatch(shell: Shell, line: str) -> None:
    name, _, arg = line.partition(" ")
    found = COMMANDS.get(name)
    if found is not None:
        await found[0](shell, arg.strip())
        return
    later = next((m for m, names in LATER.items() if name in names.split()), None)
    if later:
        shell.say(f"{name} arrives in {later}")
    else:
        shell.say(f"unknown command {name}; /help lists them")


@command("/help", "this list")
async def _help(shell: Shell, arg: str) -> None:
    seen: dict[str, list[str]] = {}
    for name, (_, text) in COMMANDS.items():
        seen.setdefault(text, []).append(name)
    rows = [f"  {' '.join(names):<18} {text}" for text, names in seen.items()]
    later = [f"  {names}  ({milestone})" for milestone, names in LATER.items()]
    shell.say("\n".join(["commands:", *rows, "coming:", *later]))


@command("/status", "session, model, mode, context, cost, queue")
async def _status(shell: Shell, arg: str) -> None:
    s, st, caps = shell.session, shell.status, shell.rt.provider.capabilities
    cost = "unknown" if st.cost is None else f"${st.cost:.4f}"
    rows = [
        ("session", f"{s.id} · {s.title or '(untitled)'}"),
        ("model", shell.rt.name),
        ("mode", s.mode),
        ("context", f"{st.context:,} of {caps.max_context:,} tokens"),
        ("cost", cost),
        ("queued", str(len(shell.queue))),
        ("steers", str(len(s.pending_steers))),
        ("turn", ("paused" if s.paused else "running") if shell.busy else "idle"),
        ("verify", shell.config.verify.command or "none"),
        ("tainted", "yes: shell and network ask in auto" if s.tainted else "no"),
        ("tools", ", ".join(shell.rt.tools.names())),
        ("personality", "arrives in M5"),
    ]
    shell.say("\n".join(f"  {k:<13} {v}" for k, v in rows))


@command("/model", "list and pick a model, or /model NAME to switch")
async def _model(shell: Shell, arg: str) -> None:
    if not arg:
        from edgar.cli.models import pick

        arg = await pick(shell.config, shell.setup.env, shell.ask, shell.say) or ""
        if not arg:
            return
    try:
        shell.switch(arg)
    except EdgarError as exc:
        shell.say(f"edgar: {exc}" + (f"\nhint: {exc.hint}" if exc.hint else ""))


@command("/mode", "show or set the permission mode")
async def _mode(shell: Shell, arg: str) -> None:
    if not arg:
        shell.say(f"mode: {shell.session.mode}")
    elif arg == "yolo":  # a typed confirmation, never config [PERM-9]
        typed = await shell.ask("yolo turns off every permission check. Type yolo to confirm: ")
        if typed.strip() == "yolo":
            shell.session.mode = "yolo"
        shell.say(f"mode: {shell.session.mode}")
    elif arg in get_args(Mode):
        shell.session.mode = arg
        shell.say(f"mode: {arg}")
    else:
        shell.say(f"modes: {', '.join(get_args(Mode))}")


@command("/thinking", "show or hide reasoning")
async def _thinking(shell: Shell, arg: str) -> None:
    shell.renderer.show_thinking = not shell.renderer.show_thinking
    state = "shown" if shell.renderer.show_thinking else "hidden"
    note = "" if shell.rt.provider.capabilities.reasoning else "; this model streams none"
    shell.say(f"reasoning {state}{note}")  # [CLI-21]


@command("/queue", "list the queue, /queue TEXT to add, /queue clear")
async def _queue(shell: Shell, arg: str) -> None:
    if arg == "clear":
        shell.queue.clear()
        shell.status.queued = 0
    elif arg:
        shell.submit(arg)
        return
    items = [f"  {i}. {text}" for i, text in enumerate(shell.queue, 1)]
    shell.say("\n".join(items) or "queue empty")


@command("/steer", "correct the running turn at its next safe point")
async def _steer(shell: Shell, arg: str) -> None:
    if not arg:
        shell.say("usage: /steer TEXT")
    elif shell.busy:
        shell.session.steer(arg)
        shell.say("steer pending: it lands before the next request")
    else:
        shell.submit(arg)  # after the turn has ended, a steer is the next turn


@command("/btw", "a side question; the conversation is untouched")
async def _btw(shell: Shell, arg: str) -> None:
    if arg:
        shell.ask_aside(arg)
    else:
        shell.say("usage: /btw QUESTION")


@command("/stop", "cancel the running turn, as Ctrl-C does")
async def _stop(shell: Shell, arg: str) -> None:
    if shell.busy:
        shell.pending_input = shell.stop()
        await asyncio.sleep(0)
    else:
        shell.say("nothing is running")


@command("/pause", "hold the turn at its next safe point")
async def _pause(shell: Shell, arg: str) -> None:
    if not shell.busy:
        shell.say("nothing is running")
        return
    shell.session.pause()
    shell.rt.bus.emit(Paused(turn_id=shell.session.id))
    shell.say("pausing: what is in flight finishes, then the turn waits; /resume")


@command("/resume", "continue a paused turn")
async def _resume(shell: Shell, arg: str) -> None:
    if shell.session.paused:
        shell.session.resume()
        shell.rt.bus.emit(Resumed(turn_id=shell.session.id))
    else:
        shell.say("nothing is paused")


@command("/cost", "tokens and cost so far")
async def _cost(shell: Shell, arg: str) -> None:
    cost = shell.status.cost
    shown = "unknown (a model without a price was used)" if cost is None else f"${cost:.4f}"
    shell.say(f"session cost: {shown}; context now {shell.status.context:,} tokens")


@command("/title", "show or set the session title")
async def _title(shell: Shell, arg: str) -> None:
    if arg:
        shell.session.title = arg[:60]
    shell.say(f"title: {shell.session.title or '(untitled)'}")


@command("/new", "start a new session")
async def _new(shell: Shell, arg: str) -> None:
    if shell.busy:
        shell.say("a turn is running; /stop it first")
        return
    old = shell.session
    shell.session = Session(cwd=old.cwd, model=old.model, mode=old.mode)
    shell.status.context = 0
    shell.say(f"new session {shell.session.id} (sessions are saved to disk from M5)")


@command("/clear", "clear the screen and start a new session")
async def _clear(shell: Shell, arg: str) -> None:
    if not shell.busy:
        shell.printer.clear()
    await _new(shell, arg)


@command("/quit /exit", "leave")
async def _quit(shell: Shell, arg: str) -> None:
    shell.done = True
