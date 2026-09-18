"""The sandbox backends: what argv they build, and what a real one enforces
[PERM-15].

A backend cannot be started on a machine that does not have it, so what every
platform checks is the *command line* — the bwrap argv and the seatbelt profile
are asserted here whatever the OS, because a wrong flag is the whole bug. The
one real execution test runs only where macOS's `sandbox-exec` exists; there is
no matching Linux one on this repo's build machines, and the roadmap's single
permitted platform condition is exactly that.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from edgar.core.errors import ConfigError
from edgar.core.events import EventBus
from edgar.permissions.policy import Deny, Policy, decide, network_allowed
from edgar.sandbox.base import BACKENDS, backend, best
from edgar.sandbox.bwrap import Bubblewrap
from edgar.sandbox.none import Nothing
from edgar.sandbox.seatbelt import Seatbelt
from edgar.tools.base import ToolContext, ToolSchema
from edgar.tools.builtin.shell import Shell, confined

ARGV = ["/bin/sh", "-c", "echo hi"]


def test_none_changes_nothing_at_all() -> None:
    nothing = Nothing()
    assert nothing.available() is True  # the default has to work everywhere
    assert nothing.wrap(ARGV, cwd=Path("/w"), writable=[Path("/w")], network=False) == ARGV


def test_no_backend_means_the_plain_command() -> None:
    assert confined(None, ARGV, cwd=Path("/w"), blob_dir=Path("/w/b"), network=True) == ARGV


def test_the_writable_set_is_the_harness_choice_not_the_models(tmp_path: Path) -> None:
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    out = confined(Seatbelt(), ARGV, cwd=tmp_path, blob_dir=blobs, network=True)
    profile = out[2]
    assert f'(allow file-write* (subpath "{tmp_path.as_posix()}"))' in profile
    assert f'(allow file-write* (subpath "{blobs.as_posix()}"))' in profile


def test_bwrap_binds_the_root_read_only_and_the_named_roots_writable(tmp_path: Path) -> None:
    out = Bubblewrap().wrap(ARGV, cwd=tmp_path, writable=[tmp_path], network=True)
    assert out[:2] == ["bwrap", "--ro-bind"]
    assert out[out.index("--bind") + 1 : out.index("--bind") + 3] == [str(tmp_path)] * 2
    assert out[-3:] == ARGV
    assert out[out.index("--chdir") + 1] == str(tmp_path)


def test_bwrap_unshares_the_network_only_when_the_decision_said_no(tmp_path: Path) -> None:
    denied = Bubblewrap().wrap(ARGV, cwd=tmp_path, writable=[], network=False)
    allowed = Bubblewrap().wrap(ARGV, cwd=tmp_path, writable=[], network=True)
    assert "--unshare-net" in denied
    assert "--unshare-net" not in allowed


def test_bwrap_skips_a_writable_root_that_does_not_exist(tmp_path: Path) -> None:
    # bwrap refuses to start at all if a bind source is missing, and a blob
    # directory is only made when something spills.
    out = Bubblewrap().wrap(ARGV, cwd=tmp_path, writable=[tmp_path / "nope"], network=True)
    assert "--bind" not in out


def test_the_seatbelt_profile_takes_writes_away_before_giving_any_back() -> None:
    lines = Seatbelt().profile([Path("/w")], network=True).splitlines()
    assert lines[:3] == ["(version 1)", "(allow default)", "(deny file-write*)"]
    assert lines.index("(deny file-write*)") < lines.index('(allow file-write* (subpath "/w"))')
    assert "(deny network*)" not in lines


def test_the_seatbelt_profile_denies_the_network_when_the_decision_said_no() -> None:
    assert "(deny network*)" in Seatbelt().profile([Path("/w")], network=False)


def test_a_quote_in_a_path_cannot_close_the_profile_string() -> None:
    # A directory really can be named `"); (allow file-write* (subpath "/`.
    profile = Seatbelt().profile([Path('/w/a"b')], network=False)
    assert '(allow file-write* (subpath "/w/a\\"b"))' in profile
    assert profile.count("(allow file-write*") == 2  # the root above, and /dev


def test_an_unknown_backend_names_the_ones_that_exist() -> None:
    with pytest.raises(ConfigError) as caught:
        backend("chroot")
    assert "chroot" in str(caught.value)
    assert all(name in (caught.value.hint or "") for name in BACKENDS)


def test_a_backend_this_machine_cannot_run_fails_the_session_start() -> None:
    # The other platform's backend, whichever platform this is: never a quiet `none`.
    absent = "seatbelt" if sys.platform.startswith("linux") else "bwrap"
    with pytest.raises(ConfigError) as caught:
        backend(absent)
    assert "not available on this machine" in str(caught.value)


def test_container_is_named_as_not_built_rather_than_pretended() -> None:
    with pytest.raises(ConfigError) as caught:
        backend("container")
    assert "not built yet" in (caught.value.hint or "")


def test_doctor_only_ever_recommends_a_backend_that_is_really_here() -> None:
    assert best() in BACKENDS
    assert backend(best()).available() if best() != "none" else best() == "none"


@pytest.mark.parametrize(
    ("mode", "tainted", "expected"),
    [
        ("yolo", True, True),  # yolo allows before anything else is read
        ("yolo", False, True),
        ("auto", False, True),
        ("auto", True, False),  # taint tightens [PERM-11]
        ("ask", True, False),
        ("read-only", False, False),
        ("read-only", True, False),
    ],
)
def test_the_sandbox_is_told_what_the_engine_decided(
    mode: str, tainted: bool, expected: bool
) -> None:
    assert network_allowed(mode, tainted) is expected


def test_network_is_never_granted_where_the_engine_would_not_allow_it(tmp_path: Path) -> None:
    # The sandbox enforces a decision already made, so it may be tighter than the
    # engine but never looser: wherever `decide()` refuses the network outright,
    # `network_allowed` must say no too. An Ask is not a refusal — by the time a
    # backend wraps the argv, the human has already answered it.
    fetch = ToolSchema("fetch", "", {"type": "object"}, "builtin", "builtin", "network")
    for mode in ("read-only", "ask", "auto", "yolo"):
        for tainted in (False, True):
            p = Policy(mode=mode, cwd=tmp_path, home=tmp_path, interactive=True, tainted=tainted)
            refused = isinstance(decide(fetch, _subject("https://example.com"), p), Deny)
            assert not (network_allowed(mode, tainted) and refused)


def _subject(text: str):  # type: ignore[no-untyped-def]
    from edgar.permissions.matcher import Subject

    return Subject(text)


@pytest.mark.skipif(not Seatbelt().available(), reason="macOS sandbox-exec only")
def test_seatbelt_really_stops_a_write_outside_the_allowed_roots(tmp_path: Path) -> None:
    # The one test that runs a confined process for real, on the one platform this
    # repo's machine can do it on.
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    result = _shell(f"echo in > inside.txt; echo out > {outside}/out.txt", project)
    assert (project / "inside.txt").exists()  # the project stays writable
    assert not (outside / "out.txt").exists()
    assert "not permitted" in result.text.lower()


@pytest.mark.skipif(not Seatbelt().available(), reason="macOS sandbox-exec only")
def test_seatbelt_really_stops_the_network_when_the_decision_said_no(tmp_path: Path) -> None:
    result = _shell("echo hi > /dev/tcp/127.0.0.1/9 && echo REACHED", tmp_path, network=False)
    assert "REACHED" not in result.text


def _shell(command: str, cwd: Path, network: bool = True):  # type: ignore[no-untyped-def]
    tool = Shell("/bin/sh", Seatbelt())
    ctx = ToolContext(
        cwd=cwd,
        bus=EventBus(),
        blob_dir=cwd / ".edgar" / "blobs",
        max_output_tokens=4000,
        network=network,
    )
    return asyncio.run(tool.run({"command": command}, ctx))
