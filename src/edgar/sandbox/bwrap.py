"""`bwrap`: bubblewrap on Linux. Everything readable, only the named roots
writable, and no network namespace unless the decision said yes [PERM-15].
"""

# The argv reads in the order bubblewrap applies it, which is why it is built in
# that order rather than grouped by topic:
#
#   1. --ro-bind / /      the whole filesystem, read-only. $HOME included, which
#                         is the "home read-only" half of the requirement.
#      --dev /dev, --proc /proc, --tmpfs /tmp   the three it cannot borrow read-only
#   2. --bind <root> <root> per writable root. A later bind wins over an earlier
#      one, so these are what turn the project back into read-write.
#   3. --unshare-net only when the decision said no. Never the other way round:
#      a backend does not grant network, it only takes it away.
#   4. --die-with-parent, so a confined process cannot outlive the turn.

from __future__ import annotations

import shutil
import sys
from collections.abc import Sequence
from pathlib import Path


class Bubblewrap:
    name = "bwrap"

    def available(self) -> bool:
        return sys.platform.startswith("linux") and shutil.which("bwrap") is not None

    def wrap(
        self, argv: Sequence[str], *, cwd: Path, writable: Sequence[Path], network: bool
    ) -> list[str]:
        out = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
        out += ["--tmpfs", "/tmp"]
        for root in writable:
            # A root that does not exist yet is skipped: bwrap fails on a missing
            # bind source, and refusing to run at all would be worse than running
            # with one fewer writable place, which is the tighter of the two.
            if root.exists():
                out += ["--bind", str(root), str(root)]
        if not network:
            out += ["--unshare-net"]
        out += ["--unshare-uts", "--unshare-ipc", "--die-with-parent", "--chdir", str(cwd), "--"]
        return [*out, *argv]
