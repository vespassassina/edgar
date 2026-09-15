"""Hooks: shell commands the harness runs at lifecycle points, declared as
`[[hooks]]` in config or an extension's `hooks.toml` [EXT-4, EXT-5].

Only `pre_tool` can stop anything: exit 2 denies, with stderr as the reason
shown to the model; any other failure or timeout also denies, so a broken hook
fails closed rather than silently letting a call through [EXT-6]. Every other
event is observation only, fired and forgotten: its exit code and output are
never read, and nothing it prints reaches the model or memory [EXT-7].
"""

from __future__ import annotations

import asyncio
import json
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from edgar.core.errors import ConfigError
from edgar.core.events import Event, EventBus, HookRan

EVENTS = frozenset(
    {"session_start", "pre_tool", "post_tool", "turn_end", "verify_finished", "session_end"}
)
# Which bus event fires which non-veto hook event, since only pre_tool needs a
# call site of its own (tools/execute.py); the rest ride events already emitted.
_OBSERVES = {
    "SessionStarted": "session_start",
    "ToolFinished": "post_tool",
    "TurnFinished": "turn_end",
    "VerifyFinished": "verify_finished",
    "SessionEnded": "session_end",
}


@dataclass(frozen=True, slots=True)
class Hook:
    event: str
    command: tuple[str, ...]
    match: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 30.0


def from_config(later: dict[str, Any]) -> tuple[Hook, ...]:
    """`[[hooks]]` arrives in `Config.later["hooks"]` (config/schema.py's LATER)."""
    raw = later.get("hooks", [])
    if not isinstance(raw, list):
        raise ConfigError('[[hooks]] must be an array of tables, written "[[hooks]]"')
    return tuple(_hook(i, entry) for i, entry in enumerate(raw))


def from_extension(folder: Path) -> tuple[Hook, ...]:
    """An extension's own `hooks.toml`, the same `[[hooks]]` shape [EXT-1]."""
    path = folder / "hooks.toml"
    if not path.is_file():
        return ()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}") from None
    raw = data.get("hooks", [])
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: hooks must be an array of tables, written [[hooks]]")
    return tuple(_hook(i, entry) for i, entry in enumerate(raw))


def _hook(index: int, entry: Any) -> Hook:
    if not isinstance(entry, dict):
        raise ConfigError(f"[[hooks]] rule {index}: must be a table")
    event, command = entry.get("event"), entry.get("command")
    if event not in EVENTS:
        raise ConfigError(f"[[hooks]] rule {index}: event must be one of {sorted(EVENTS)}")
    ok_command = isinstance(command, list) and command and all(isinstance(c, str) for c in command)
    if not ok_command:
        raise ConfigError(f"[[hooks]] rule {index}: command must be a non-empty list of strings")
    match = entry.get("match", {})
    if not isinstance(match, dict):
        raise ConfigError(f"[[hooks]] rule {index}: match must be a table")
    return Hook(event, tuple(cast("list[str]", command)), match, float(entry.get("timeout_s", 30)))


def _matches(hook: Hook, payload: dict[str, Any]) -> bool:
    return all(str(payload.get(k)) == v for k, v in hook.match.items())


async def _run(hook: Hook, payload: dict[str, Any], cwd: Path) -> tuple[int, str]:
    # The event as JSON on stdin [EXT-5].
    try:
        proc = await asyncio.create_subprocess_exec(
            *hook.command,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _out, err = await asyncio.wait_for(
            proc.communicate(json.dumps(payload).encode()), hook.timeout_s
        )
        return proc.returncode or 0, err.decode(errors="replace")
    except (OSError, TimeoutError):
        return 1, f"{hook.command[0]} failed to run or timed out"


async def veto(
    hooks: tuple[Hook, ...], payload: dict[str, Any], *, cwd: Path, bus: EventBus
) -> str | None:
    """None allows the call; anything else is the reason a `pre_tool` hook denied
    it [EXT-6]."""
    for hook in hooks:
        if hook.event != "pre_tool" or not _matches(hook, payload):
            continue
        code, err = await _run(hook, payload, cwd)
        bus.emit(HookRan(event="pre_tool", command=hook.command[0], ok=code == 0, vetoed=code != 0))
        if code != 0:
            return err.strip() or f"{hook.command[0]} vetoed this call"
    return None


_running: set[asyncio.Task[None]] = set()  # keeps a fired hook alive; asyncio holds no other ref


def listener(hooks: tuple[Hook, ...], cwd: Path, bus: EventBus) -> Callable[[Event], None]:
    """Subscribed once per session: dispatches every non-veto event to the hooks
    that match it, fired as a background task so nothing here can block or
    change what already happened [EXT-6, EXT-7]."""
    by_event = [h for h in hooks if h.event != "pre_tool"]

    def on_event(event: Event) -> None:
        name = _OBSERVES.get(event.name)
        if name is None:
            return
        payload = {**event.to_dict(), "tool": getattr(event, "tool", "")}
        for hook in by_event:
            if hook.event == name and _matches(hook, payload):
                task = asyncio.ensure_future(_fire(hook, payload, cwd, bus))
                _running.add(task)
                task.add_done_callback(_running.discard)

    return on_event


async def _fire(hook: Hook, payload: dict[str, Any], cwd: Path, bus: EventBus) -> None:
    code, _ = await _run(hook, payload, cwd)
    bus.emit(HookRan(event=hook.event, command=hook.command[0], ok=code == 0, vetoed=False))
