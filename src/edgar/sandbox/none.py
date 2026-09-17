"""`none`: no walls at all, the default, and the one backend that runs everywhere.

It is not a stub. It is the honest name for what edgar did before M21 and still
does unless a human configures otherwise, and it is what core tests use so they
run on Windows too [PERM-15, NFR-6].
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class Nothing:
    name = "none"

    def available(self) -> bool:
        return True  # running a process plainly is always possible

    def wrap(
        self, argv: Sequence[str], *, cwd: Path, writable: Sequence[Path], network: bool
    ) -> list[str]:
        # The arguments are accepted and ignored on purpose: a caller must not have
        # to know which backend it has, and a backend that silently dropped them
        # while claiming to confine would be the bug this milestone is about.
        return list(argv)
