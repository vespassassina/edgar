# Reads the event as JSON from stdin, finds that session's transcript under
# .edgar/sessions/ (the hook's cwd is always the project root [EXT-5]), and
# delivers the last assistant reply: to a webhook if EDGAR_NOTIFY_WEBHOOK is
# set, otherwise to the desktop notifier. Runs through the same subprocess
# call any hook does: no shell, started directly, nothing read back but the
# exit code, so a delivery failure here changes nothing about the session it
# reports on.
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

MAX_CHARS = 500


def last_reply(session_id: str) -> str:
    path = Path(".edgar/sessions") / f"{session_id}.jsonl"
    if not path.is_file():
        return "(transcript not found)"
    text = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("type") == "message" and entry.get("role") == "assistant":
            text = "".join(b["text"] for b in entry["content"] if b["kind"] == "TextBlock")
    return (text or "(no reply)")[:MAX_CHARS]


def deliver(summary: str) -> None:
    webhook = os.environ.get("EDGAR_NOTIFY_WEBHOOK")
    if webhook:
        body = json.dumps({"text": summary}).encode()
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(webhook, data=body, headers=headers)
        urllib.request.urlopen(req, timeout=10)
    elif platform.system() == "Darwin":
        script = f'display notification {json.dumps(summary)} with title "edgar"'
        subprocess.run(["osascript", "-e", script], check=False)
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", "edgar", summary], check=False)


event = json.loads(sys.stdin.read())
deliver(last_reply(event["session_id"]))
