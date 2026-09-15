# Reads the event as JSON from stdin and appends one line to audit.log beside
# this file. Runs through the same subprocess call any hook does: no shell,
# started directly, with the event on stdin and nothing read back but the
# exit code (turn_end is observation only, so even a crash here changes
# nothing about the turn).
from __future__ import annotations

import json
import sys
from pathlib import Path

event = json.loads(sys.stdin.read())
line = f"{event.get('name', '?')} {event.get('tool', '')}\n"
with (Path(__file__).parent / "audit.log").open("a", encoding="utf-8") as f:
    f.write(line)
