"""`seatbelt`: macOS `sandbox-exec`, with a profile generated per call [PERM-15].

The same shape as `bwrap`: everything readable, only the named roots writable,
and the network denied unless the decision said yes.
"""

# The profile, in the order it is read (later rules win in SBPL):
#
#   (allow default)                   start from a normal process ...
#   (deny file-write*)                ... then take every write away ...
#   (allow file-write* (subpath ...)) ... and give back only the named roots
#   (allow file-write* (subpath "/dev"))   /dev/null and friends, never data
#   (deny network*)                   only when the decision said no
#
# `sandbox-exec` is deprecated by Apple but present on every supported macOS, and
# it is what the platform offers. `available()` checks for the binary rather than
# assuming it, so a future macOS that drops it makes `backend()` fail loudly
# instead of running a command everyone believes is confined.

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

EXEC = "/usr/bin/sandbox-exec"


def _quoted(path: Path) -> str:
    # SBPL is a macOS-only syntax and always takes forward-slash paths, so
    # `as_posix()` keeps the profile identical on every host platform that
    # can run these tests, even though `available()` gates real use to
    # darwin. SBPL string literals are C-like: a quote or backslash in the
    # path must not be able to close the string and add a rule of its own.
    return path.as_posix().replace("\\", "\\\\").replace('"', '\\"')


class Seatbelt:
    name = "seatbelt"

    def available(self) -> bool:
        return sys.platform == "darwin" and Path(EXEC).exists()

    def profile(self, writable: Sequence[Path], network: bool) -> str:
        lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
        lines += [f'(allow file-write* (subpath "{_quoted(root)}"))' for root in writable]
        lines.append('(allow file-write* (subpath "/dev"))')
        if not network:
            lines.append("(deny network*)")
        return "\n".join(lines)

    def wrap(
        self, argv: Sequence[str], *, cwd: Path, writable: Sequence[Path], network: bool
    ) -> list[str]:
        # The profile goes in the argv, not a temp file: nothing to leave behind,
        # and nothing for another process to swap between writing and running it.
        return [EXEC, "-p", self.profile(writable, network), *argv]
