"""Slash commands [CLI-14, CLI-22, CLI-25, CLI-27, CLI-28].

Each command is a small function over the `Shell`. Commands whose machinery lands
in a later milestone say which one, rather than pretending to work.
"""

# The session commands all end the same way: a JSONL file on disk is replayed and
# the shell opens it (_switch). /load names one, /fork writes a one-line file that
# points into this session, and /load PATH first adopts a /save file as a new one.

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import get_args

from edgar.cli.memory import listing as fact_listing
from edgar.cli.memory import said
from edgar.cli.repl import Shell
from edgar.cli.setup import spending
from edgar.config.schema import Mode
from edgar.context.compact import compact, rewind, turn_starts
from edgar.context.tokens import message_text
from edgar.core.errors import EdgarError
from edgar.core.events import FactSaved, Paused, Resumed
from edgar.core.session import Session
from edgar.storage.transcript import (
    adopt,
    conversation,
    find,
    fork,
    listing,
    replay,
    save,
    sessions_dir,
    start,
)

Command = Callable[[Shell, str], Awaitable[None]]
COMMANDS: dict[str, tuple[Command, str]] = {}

# Commands still owed, and when; plan mode moved to v2 in ADR-0053.
LATER = {"M9": "/agents", "M10": "/skills /tools", "M11": "/init", "v2": "/plan /go"}


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


BROWSER = """/browser needs a [browser] block in .edgar/config.toml. Either name a
command tool you already have:

  [browser]
  tool = "browse"

or the MCP server that drives one, which edgar starts only when you type /browser:

  [browser]
  command = "npx"
  args = ["@playwright/mcp@X.Y.Z"]   # pin the version you reviewed"""


@command("/browser", "connect the browser [browser] names [CLI-29]")
async def _browser(shell: Shell, arg: str) -> None:
    # A browser is an ordinary tool or an ordinary MCP server; /browser only starts
    # what the config already names, and never picks one for you [ADR-0036, PRV-15].
    from edgar.tools.builtin.tool_search import searchable
    from edgar.tools.mcp.client import FAILURES

    tools, named = shell.rt.tools, shell.config.browser.tool
    if named:
        ready = tools.get(named) is not None
        shell.say(f"/browser: the {named} tool is ready" if ready else f"no tool named {named!r}")
        return
    server = shell.setup.browser
    if server is None:
        shell.say(BROWSER)
        return
    try:
        found = await server.discover()
    except FAILURES as exc:
        shell.say(f"the browser did not start: {exc}")
        return
    shell.setup.servers.append(server)  # so it stops when the session does
    tools.add(found)
    searchable(tools, [])
    waiting = [t.schema.name for t in found if t.schema.name in tools.deferred]
    how = " · tool_search loads them" if waiting else ""
    shell.say(f"browser connected: {len(found)} tools{how}")


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
    today = sum(c for _, c in spending(shell.setup.home).spent())  # every project [BUD-6]
    shell.say(
        f"session cost: {shown}; today ${today:.4f}; context now {shell.status.context:,} tokens"
    )


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


@command("/load", "open a session: /load ID (a unique start is enough) or a /save file")
async def _load(shell: Shell, arg: str) -> None:
    if not arg:
        shell.say("usage: /load ID|PATH; /sessions lists them")
    elif _idle(shell):
        root = shell.session.cwd
        await _switch(
            shell, lambda: adopt(root, root / arg) if (root / arg).is_file() else None, arg
        )


@command("/fork", "branch this session into a new one; /fork N starts from the end of turn N")
async def _fork(shell: Shell, arg: str) -> None:
    if _idle(shell):
        which = f"{shell.session.id}@{arg}" if arg else shell.session.id
        await _switch(shell, lambda: fork(shell.session.cwd, which), arg)


async def _switch(shell: Shell, make: Callable[[], Path | None], arg: str) -> None:
    # 1. The file to open: the one `make` writes, else the session `arg` names.
    try:
        path = make() or find(shell.session.cwd, arg)
        session, _ = replay(path)
    except EdgarError as exc:
        shell.say(f"edgar: {exc}")
        return
    # 2. Open it in the current mode, show what it holds, and say which it is.
    session.mode = shell.session.mode
    shell.open(session)
    shell.renderer.show(session.transcript)
    shell.say(f"now in {session.id} · {session.title or '(untitled)'}")


@command("/save", "write the session to one file to share or /load: /save [PATH]")
async def _save(shell: Shell, arg: str) -> None:
    own = sessions_dir(shell.session.cwd) / f"{shell.session.id}.jsonl"
    out = shell.session.cwd / (arg or f"edgar-{shell.session.id}.jsonl")
    if not own.is_file():
        shell.say("nothing to save yet")
        return
    save(own, out)
    shell.say(f"saved to {out}: spilled output included, secrets redacted (check before sharing)")


@command("/history", "the whole conversation from the record, compacted parts included")
async def _history(shell: Shell, arg: str) -> None:
    own = sessions_dir(shell.session.cwd) / f"{shell.session.id}.jsonl"
    lines = [f"{m.role}: {message_text(m)}" for m in conversation(own)] if own.is_file() else []
    shell.say("\n\n".join(lines) or "nothing yet")


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


@command("/remember", "remember TEXT for this project's future sessions [MEM-23]")
async def _remember(shell: Shell, arg: str) -> None:
    # Typed by a human, so it is active at once; the prompt changes from the next
    # session, so this one's cached prefix holds [MEM-6].
    if not arg:
        shell.say("usage: /remember TEXT")
        return
    fact = shell.setup.memory.add(arg, shell.setup.scope)
    if fact.status == "active":
        shell.rt.bus.emit(FactSaved(fact_id=fact.id, provenance=fact.provenance))
    shell.say(said(fact))


@command("/memory", "what is remembered; `edgar memory` edits, reviews and undoes")
async def _memory(shell: Shell, arg: str) -> None:
    s = shell.setup
    # One "- fact" line per pinned fact; a fact is always one line.
    kept = next((p.text.count("\n- ") for p in s.pinned if p.name == "memory"), 0)
    head = f"pinned in this session's prompt: {kept} of {shell.config.memory.pinned_max}"
    shell.say(head + "\n" + fact_listing(s.memory, s.scope, s.root))


@command("/quit /exit", "leave")
async def _quit(shell: Shell, arg: str) -> None:
    shell.done = True
