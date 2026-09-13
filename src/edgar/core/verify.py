"""The verify gate: done means your check passed [VER-1..6, ADR-0014].

When the model stops calling tools after a turn that changed something, the
declared command runs. Exit 0 ends the turn. Anything else goes back to the
model as verification feedback, head and tail kept, and the turn goes on, up to
`max_attempts` runs. The harness runs the check itself; what the model says
about the check does not count.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from edgar.core.events import EventBus, VerifyFinished, VerifyStarted
from edgar.tools.builtin.shell import run_argv, shell_argv
from edgar.tools.spill import spill


@dataclass(frozen=True, slots=True)
class Check:
    command: str
    max_attempts: int = 2
    program: str = "auto"  # [shell] program


async def verify(
    check: Check, attempt: int, *, cwd: Path, blob_dir: Path, bus: EventBus, max_tokens: int
) -> str | None:
    """None when the check passes; otherwise the feedback for the model."""
    bus.emit(VerifyStarted(command=check.command, attempt=attempt))
    started = time.monotonic()
    code, output = await run_argv(shell_argv(check.program, check.command), cwd)
    duration = round((time.monotonic() - started) * 1000)
    bus.emit(VerifyFinished(ok=code == 0, exit_code=code, attempt=attempt, duration_ms=duration))
    if code == 0:
        return None
    kept = spill(
        output, max_tokens=max_tokens, blob_dir=blob_dir, name=f"verify_{attempt}", root=cwd
    )
    return (
        f"Verification failed: `{check.command}` exited {code} (attempt {attempt} of "
        f"{check.max_attempts}). Fix the cause; the check runs again when you stop.\n"
        f"{kept.text}"
    )
