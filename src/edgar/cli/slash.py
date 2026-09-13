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
from edgar.context.compact import compact, rewind, turn_starts
from edgar.core.errors import EdgarError
from edgar.core.events import Paused, Resumed
from edgar.core.session import Session
from edgar.storage.transcript import find, listing, replay, start

Command = Callable[[Shell, str], Awaitable[None]]
COMMANDS: dict[str, tuple[Command, str]] = {}

LATER = {
    "M8": "/browser",
    "M6": "/skills /tools",
    "v1": "/plan /go /save /history /fork /remember /memory /agents /init",
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
    cost = "unknown" if s.cost is None else f"${s.cost:.4f}"
    persona = [str(p.source) for p in shell.setup.pinned if p.name == "personality"]
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
        ("personality", persona[0] if persona else "none"),
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
    cost = shell.session.cost
    shown = "unknown (a model without a price was used)" if cost is None else f"${cost:.4f}"
    shell.say(f"session cost: {shown}; context now {shell.status.context:,} tokens")


@command("/title", "show or set the session title")
async def _title(shell: Shell, arg: str) -> None:
    if arg:
        shell.session.title = arg[:60]
        shell.session.record({"type": "title", "text": arg[:60]})
    shell.say(f"title: {shell.session.title or '(untitled)'}")


def _idle(shell: Shell) -> bool:
    if shell.busy:
        shell.say("a turn is running; /stop it first")
    return not shell.busy


@command("/compact", "compact the conversation now; /compact FOCUS steers the summary")
async def _compact(shell: Shell, arg: str) -> None:
    if not _idle(shell):
        return
    before = list(shell.session.transcript)
    try:
        await compact(shell.session, shell.rt, force=True, focus=arg or None)  # [CTX-7]
    except EdgarError as exc:
        shell.say(f"edgar: {exc}" + (f"\nhint: {exc.hint}" if exc.hint else ""))
    if shell.session.transcript == before:
        shell.say("nothing to compact: every turn is recent (context.keep_last_turns)")


@command("/reset", "empty the conversation; the session, model and title stay")
async def _reset(shell: Shell, arg: str) -> None:
    if _idle(shell):
        shell.session.transcript = []
        shell.session.record({"type": "reset"})
        shell.status.context = 0
        shell.say("conversation emptied")


@command("/undo", "remove the last N turns (default 1); files stay as they are")
async def _undo(shell: Shell, arg: str) -> None:
    if not (arg or "1").isdigit() or int(arg or "1") < 1:
        shell.say("usage: /undo [N]")
    elif _idle(shell):
        _rewind(shell, int(arg or "1"))


@command("/retry", "undo the last turn and send its prompt again")
async def _retry(shell: Shell, arg: str) -> None:
    if _idle(shell):
        prompt = _rewind(shell, 1)
        if prompt:
            shell.submit(prompt)


def _rewind(shell: Shell, turns: int) -> str:
    """Whole turns go; what `write` and `edit` did in them stays on disk [CLI-26]."""
    s = shell.session
    starts = turn_starts(s.transcript)
    if not starts:
        shell.say("nothing to undo")
        return ""
    first = s.transcript[starts[-min(turns, len(starts))]].text
    s.transcript, files = rewind(s.transcript, turns)
    s.record({"type": "undo", "turns": turns, "files": files})
    kept = f"; files changed in them stay changed: {', '.join(files)}" if files else ""
    shell.say(f"undid {min(turns, len(starts))} turn(s){kept}")
    return first


@command("/sessions", "list this project's sessions")
async def _sessions(shell: Shell, arg: str) -> None:
    shell.say("\n".join(listing(shell.session.cwd)) or "no sessions yet")


@command("/load", "open a session: /load ID (a unique start is enough)")
async def _load(shell: Shell, arg: str) -> None:
    if not arg:
        shell.say("usage: /load ID; /sessions lists them")
    elif _idle(shell):
        try:
            session, _ = replay(find(shell.session.cwd, arg))
        except EdgarError as exc:
            shell.say(f"edgar: {exc}")
            return
        session.mode = shell.session.mode
        shell.open(session)
        shell.renderer.show(session.transcript)
        shell.say(f"loaded {session.id} · {session.title or '(untitled)'}")


@command("/new", "start a new session; the old one stays on disk")
async def _new(shell: Shell, arg: str) -> None:
    if _idle(shell):
        old = shell.session
        shell.open(start(Session(cwd=old.cwd, model=old.model, mode=old.mode)))
        shell.say(f"new session {shell.session.id}")


@command("/clear", "clear the screen and start a new session")
async def _clear(shell: Shell, arg: str) -> None:
    if not shell.busy:
        shell.printer.clear()
    await _new(shell, arg)


@command("/quit /exit", "leave")
async def _quit(shell: Shell, arg: str) -> None:
    shell.done = True
