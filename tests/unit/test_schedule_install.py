"""install()/uninstall() route by platform.system() [SCH-3]. Every branch is
exercised the same way on all three CI platforms: subprocess.run is
monkeypatched, so nothing here actually touches this host's real scheduler."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

import pytest

from edgar.schedule import install as m


class Recorder:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, args: object, **kwargs: object) -> Any:
        self.calls.append((args, kwargs))

        class Result:
            stdout = ""

        return Result()


def test_render_launchd_names_the_project_and_its_working_directory(tmp_path: Path) -> None:
    text = m.render_launchd(tmp_path)
    assert str(tmp_path.resolve()) in text
    assert m.project_id(tmp_path) in text


def test_render_cron_carries_a_marker_scoped_to_the_project(tmp_path: Path) -> None:
    line = m.render_cron(tmp_path)
    assert f"# {m.TASK_NAME}:{m.project_id(tmp_path)}" in line
    assert str(tmp_path.resolve()) in line


def test_render_schtasks_creates_by_default_and_deletes_when_asked(tmp_path: Path) -> None:
    assert "/create" in m.render_schtasks(tmp_path)
    assert "/delete" in m.render_schtasks(tmp_path, remove=True)


def test_project_id_is_stable_across_calls(tmp_path: Path) -> None:
    assert m.project_id(tmp_path) == m.project_id(tmp_path)


@pytest.mark.parametrize("system", ["Darwin", "Linux", "Windows"])
def test_install_and_uninstall_route_to_the_right_host_mechanism(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    rec = Recorder()
    monkeypatch.setattr(subprocess, "run", rec)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # launchd's plist goes under a fake home

    m.install(tmp_path / "project")
    m.uninstall(tmp_path / "project")

    tools = {c[0][0] for c in rec.calls}
    expected = {"Darwin": "launchctl", "Linux": "crontab", "Windows": "schtasks"}[system]
    assert expected in tools
