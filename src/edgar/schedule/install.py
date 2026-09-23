# install.py: one host scheduler entry that runs `edgar tick` every minute for
# one project [SCH-3]. render_*() are pure — text or an argv list, never
# touching the host — so every platform's shape is tested from any one
# machine; install()/uninstall() are the one impure step, routed by
# `platform.system()`.

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from pathlib import Path

LABEL = "com.edgar.tick"
TASK_NAME = "edgar-tick"


def project_id(project: Path) -> str:
    return hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:12]


def render_launchd(project: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}.{project_id(project)}</string>
  <key>WorkingDirectory</key><string>{project.resolve()}</string>
  <key>ProgramArguments</key><array>
    <string>{sys.executable}</string><string>-m</string><string>edgar</string><string>tick</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><false/>
</dict></plist>
"""


def render_cron(project: Path) -> str:
    marker = f"# {TASK_NAME}:{project_id(project)}"
    return f"* * * * * cd {project.resolve()} && {sys.executable} -m edgar tick  {marker}\n"


def render_schtasks(project: Path, *, remove: bool = False) -> list[str]:
    if remove:
        return ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    run = f'cmd /c "cd /d {project.resolve()} && {sys.executable} -m edgar tick"'
    return ["schtasks", "/create", "/sc", "MINUTE", "/mo", "1", "/tn", TASK_NAME, "/tr", run, "/f"]


def _plist_path(project: Path) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.{project_id(project)}.plist"


def install(project: Path) -> str:
    system = platform.system()
    if system == "Darwin":
        return _launchd(project, load=True)
    if system == "Windows":
        subprocess.run(render_schtasks(project), check=True)
        return f"installed: schtasks {TASK_NAME}"
    return _cron(project, remove=False)


def uninstall(project: Path) -> str:
    system = platform.system()
    if system == "Darwin":
        return _launchd(project, load=False)
    if system == "Windows":
        subprocess.run(render_schtasks(project, remove=True), check=True)
        return f"removed: schtasks {TASK_NAME}"
    return _cron(project, remove=True)


def _launchd(project: Path, *, load: bool) -> str:
    plist = _plist_path(project)
    if load:
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(render_launchd(project), encoding="utf-8")
        subprocess.run(["launchctl", "load", str(plist)], check=True)
        return f"installed: {plist}"
    subprocess.run(["launchctl", "unload", str(plist)], check=False)
    plist.unlink(missing_ok=True)
    return f"removed: {plist}"


def _cron(project: Path, *, remove: bool) -> str:
    marker = f"# {TASK_NAME}:{project_id(project)}"
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
    lines = [ln for ln in existing.splitlines() if marker not in ln]
    if not remove:
        lines.append(render_cron(project).rstrip("\n"))
    body = "\n".join(lines) + "\n" if lines else ""
    subprocess.run(["crontab", "-"], input=body, text=True, check=True)
    return "removed: crontab entry" if remove else "installed: crontab entry"
