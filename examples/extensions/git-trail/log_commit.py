# Reads the event as JSON from stdin and appends one line to git-trail.log
# beside this file. Runs through the same subprocess call any hook does: no
# shell, started directly, with the event on stdin and nothing read back but the
# exit code — post_tool is observation only, so even a crash here changes
# nothing about the turn or what the model sees.
#
# The event carries the call's outcome (tool, ok, duration_ms), never the tool's
# output, so the commit itself is read back from git. That is the shape of every
# post_tool hook: you learn that something happened, and you go look yourself.
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

event = json.loads(sys.stdin.read())
when = datetime.now(UTC).isoformat(timespec="seconds")
if not event.get("ok"):
    line = f"{when} commit failed\n"
else:
    head = subprocess.run(
        ["git", "log", "-1", "--oneline"], capture_output=True, text=True, check=False
    )
    line = f"{when} {head.stdout.strip() or '(no commit found)'}\n"
with (Path(__file__).parent / "git-trail.log").open("a", encoding="utf-8") as f:
    f.write(line)
