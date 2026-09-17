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
from typing import TYPE_CHECKING

from edgar.core.errors import PermissionDenied
from edgar.core.events import EventBus, VerifyFinished, VerifyStarted
from edgar.permissions.policy import Deny
from edgar.sandbox.base import Sandbox
from edgar.tools.builtin.shell import Shell, confined, run_argv, shell_argv
from edgar.tools.spill import spill

if TYPE_CHECKING:
    from edgar.core.session import Session
    from edgar.permissions.guard import Guard


@dataclass(frozen=True, slots=True)
class Check:
    command: str
    max_attempts: int = 2
    program: str = "auto"  # [shell] program
    sandbox: Sandbox | None = None  # the walls the check runs inside [PERM-15]


async def authorise(check: Check, guard: Guard, session: Session, bus: EventBus) -> None:
    """The verify command is a shell call, decided before the turn starts, so a run
    that would need a prompt at the end fails now [VER-4]."""
    decision = await guard.check(
        Shell(check.program).schema,
        {"command": check.command},
        cwd=session.cwd,
        mode=session.mode,
        tainted=session.tainted,
        call_id="verify",
        bus=bus,
    )
    if isinstance(decision, Deny):
        raise PermissionDenied(
            f"the verify command `{check.command}` is not allowed: {decision.reason}",
            hint='allow it with [permissions] shell_allow = ["…"], or run with --mode ask',
        )


async def verify(
    check: Check, attempt: int, *, cwd: Path, blob_dir: Path, bus: EventBus, max_tokens: int
) -> str | None:
    """None when the check passes; otherwise the feedback for the model."""
    bus.emit(VerifyStarted(command=check.command, attempt=attempt))
    started = time.monotonic()
    # The check is a command a human declared, so it keeps the network; what the
    # backend takes away is the ability to write outside the project [PERM-15].
    argv = confined(
        check.sandbox,
        shell_argv(check.program, check.command),
        cwd=cwd,
        blob_dir=blob_dir,
        network=True,
    )
    code, output = await run_argv(argv, cwd)
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
