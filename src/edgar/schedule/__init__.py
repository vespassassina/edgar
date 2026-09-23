# edgar.schedule is v4, and removable: nothing in Core, v1, v2 or v3 imports it,
# a test proves it, and CI deletes the package and runs the suite below it
# [NFR-12]. cli/setup.py reaches self_tools() below by name, through
# import_module, the same way it reaches broker, learning and the controller
# [ADR-0015].

from __future__ import annotations

from pathlib import Path

from edgar.schedule.store import SelfSchedules
from edgar.schedule.tool import ScheduleSelfTool


def self_tools(root: Path, depth: int) -> list[ScheduleSelfTool]:
    return [ScheduleSelfTool(SelfSchedules(root / ".edgar" / "edgar.db"), depth)]
