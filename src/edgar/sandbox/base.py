"""The Sandbox port: `shell.sandbox` picks the walls a process runs inside
[PERM-15, ADR-0022].

A backend enforces a decision that has already been made. It is handed the
directories the harness says are writable and the answer `permissions/` already
gave about the network, and it turns them into the platform's own mechanism. It
never decides anything itself, and there is nothing here for a model to steer.
"""

# The port is one pure function. A backend does not run the process, it says what
# argv would run it confined; `tools/builtin/shell.py`'s `run_argv` stays the one
# place in edgar that starts a subprocess, and keeps its process-group kill.
#
# That is a deliberate change from BLUEPRINT §7.5's first sketch, which gave the
# protocol an `async run(...)`. Two reasons. A second launcher would have to
# re-implement the group kill that makes Ctrl-C work, and a launcher cannot be
# tested on a machine where the backend is absent, while argv can: the seatbelt
# profile and the bwrap command line are both asserted on every platform, which
# is most of what there is to get wrong in a sandbox.
#
#   backend(name) -> the configured backend, or a loud failure  (session start)
#   best()        -> what this machine could use                (edgar doctor)

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from edgar.core.errors import ConfigError

BACKENDS = ("none", "bwrap", "seatbelt", "container")  # the config's own list


class Sandbox(Protocol):
    name: str

    def available(self) -> bool: ...

    def wrap(
        self, argv: Sequence[str], *, cwd: Path, writable: Sequence[Path], network: bool
    ) -> list[str]: ...


def _all() -> list[Sandbox]:
    # Imported here, not at module scope: the port must not drag its adapters into
    # `edgar.cli.main` (NFR-1), and nothing outside this function names them.
    from edgar.sandbox.bwrap import Bubblewrap
    from edgar.sandbox.none import Nothing
    from edgar.sandbox.seatbelt import Seatbelt

    return [Nothing(), Bubblewrap(), Seatbelt()]


def backend(name: str) -> Sandbox:
    """The backend `shell.sandbox` names. A configured one that cannot really run
    here fails the session start rather than quietly becoming `none` [PERM-15]."""
    found = next((s for s in _all() if s.name == name), None)
    if found is None:
        listed = ", ".join(BACKENDS)
        raise ConfigError(
            f"there is no sandbox backend {name!r}",
            hint=f"[shell] sandbox is one of: {listed}. `container` is not built yet.",
        )
    if not found.available():
        raise ConfigError(
            f"[shell] sandbox = {name!r}, but it is not available on this machine",
            hint=f"install it, or set [shell] sandbox = {best()!r}, which is what "
            "`edgar doctor` recommends here.",
        )
    return found


def best() -> str:
    """The strongest backend this machine can actually run. `none` is always last
    and always works, so this never recommends something that is not there."""
    return next((s.name for s in reversed(_all()) if s.available()), "none")
