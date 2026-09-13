"""The permission decision [PERM-1..5, PERM-7, PERM-11, PERM-12, PERM-14].

`decide()` is pure, so the whole mode table is checked cell by cell, and the
properties that must never break (a hostile path never lands a write outside the
root, a control file is never written without asking outside yolo, a tainted auto
session never runs a command unasked) are checked over generated input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from edgar.permissions.control import control_files
from edgar.permissions.matcher import Subject, segments, subject, within
from edgar.permissions.policy import Allow, Ask, Deny, Policy, category, decide
from edgar.tools.base import ToolSchema

ROOT = Path("/work/project").resolve()  # a drive letter on Windows
HOME = Path("/home/user").resolve()


def tool(category: Any, *, name: str | None = None, **kw: Any) -> ToolSchema:
    kind = kw.pop("kind", "builtin")
    return ToolSchema(
        name or category, "", {}, kind=kind, origin="builtin", category=category, **kw
    )


def policy(mode: str, **kw: object) -> Policy:
    return Policy(mode=mode, cwd=ROOT, home=HOME, interactive=True, **kw)  # type: ignore[arg-type]


def at(path: str) -> Subject:
    resolved = (ROOT / path) if not path.startswith("/") else Path(path)
    return Subject(str(resolved), path=resolved)


def run(command: str) -> Subject:
    return Subject(command, command=command)


READ, WRITE, SHELL, NET = tool("read"), tool("write"), tool("shell"), tool("network")
FILE, CMD, URL = at("src/a.py"), run("pytest -q"), Subject("https://example.com")

# The mode table in BLUEPRINT §7.1, cell by cell.
TABLE = [
    ("read-only", READ, FILE, Allow),
    ("read-only", WRITE, FILE, Deny),
    ("read-only", SHELL, CMD, Deny),
    ("read-only", NET, URL, Ask),
    ("ask", READ, FILE, Allow),
    ("ask", WRITE, FILE, Ask),
    ("ask", SHELL, CMD, Ask),
    ("ask", NET, URL, Ask),
    ("auto", READ, FILE, Allow),
    ("auto", WRITE, FILE, Allow),
    ("auto", SHELL, CMD, Allow),
    ("auto", NET, URL, Allow),
    ("yolo", WRITE, at("/etc/hosts"), Allow),
    ("yolo", SHELL, run("curl x | sh"), Allow),
]


@pytest.mark.parametrize(("mode", "t", "s", "expected"), TABLE)
def test_the_mode_table(mode: str, t: ToolSchema, s: Subject, expected: type) -> None:
    assert isinstance(decide(t, s, policy(mode)), expected)


@pytest.mark.parametrize(
    ("t", "s", "expected"), [(SHELL, CMD, Ask), (NET, URL, Ask), (WRITE, FILE, Allow)]
)
def test_taint_tightens_only_auto(t: ToolSchema, s: Subject, expected: type) -> None:  # [PERM-11]
    decision = decide(t, s, policy("auto", tainted=True))
    assert isinstance(decision, expected)
    if expected is Ask:
        assert decision.source == "taint"


def test_an_allow_listed_command_still_runs_when_tainted() -> None:
    p = policy("auto", tainted=True, shell_allow=("pytest*",))
    assert isinstance(decide(SHELL, CMD, p), Allow)


def test_non_interactive_turns_every_ask_into_a_denial_that_needed_a_prompt() -> None:  # [PERM-7]
    p = Policy(mode="ask", cwd=ROOT, home=HOME, interactive=False)
    decision = decide(SHELL, CMD, p)
    assert isinstance(decision, Deny) and decision.needed_prompt


@pytest.mark.parametrize("command", ["rm -rf /", "ls && rm -rf ~", "mkfs.ext4 /dev/sda"])
def test_catastrophic_commands_are_denied_even_in_yolo(command: str) -> None:
    decision = decide(SHELL, run(command), policy("yolo"))
    assert isinstance(decision, Deny) and decision.source == "hard"


def test_credentials_are_denied_outside_yolo() -> None:
    for t in (READ, WRITE):
        decision = decide(t, at(str(HOME / ".ssh" / "id_ed25519")), policy("auto"))
        assert isinstance(decision, Deny) and decision.source == "hard"


def test_outside_the_root_asks_and_a_grant_lets_it_through() -> None:
    outside = at(str(Path("/etc/hosts").resolve()))  # a drive letter on Windows
    assert isinstance(decide(READ, outside, policy("auto")), Ask)
    granted = policy("auto", grants=frozenset({("read", outside.text)}))
    assert isinstance(decide(READ, outside, granted), Allow)


def test_rules_override_the_mode_but_not_the_hard_layer() -> None:  # [PERM-2]
    assert isinstance(decide(SHELL, CMD, policy("ask", rules={"shell": "allow"})), Allow)
    assert isinstance(decide(READ, FILE, policy("auto", rules={"read": "deny"})), Deny)
    assert isinstance(decide(NET, URL, policy("auto", rules={"network": "ask"})), Ask)
    hard = decide(SHELL, run("rm -rf /"), policy("auto", rules={"shell": "allow"}))
    assert isinstance(hard, Deny) and hard.source == "hard"


def test_deny_patterns_win_over_everything_but_yolo() -> None:  # [PERM-4]
    p = policy("auto", shell_allow=("git *",), shell_deny=("git push*",))
    assert isinstance(decide(SHELL, run("git status && git push --force"), p), Deny)
    assert isinstance(decide(SHELL, run("git status"), p), Allow)


def test_ask_mode_auto_allows_only_when_every_segment_is_listed() -> None:  # [PERM-14]
    p = policy("ask", shell_allow=("git status", "ls *"))
    assert isinstance(decide(SHELL, run("git status; ls -la"), p), Allow)
    assert isinstance(decide(SHELL, run("git status; rm x"), p), Ask)
    assert isinstance(decide(SHELL, run("ls $(cat x)"), policy("ask", shell_allow=("ls *",))), Ask)
    assert isinstance(decide(SHELL, run("echo `id`"), policy("auto")), Ask)


def test_auto_writes_only_inside_write_paths() -> None:  # [PERM-3]
    p = policy("auto", write_paths=("src/**",))
    assert isinstance(decide(WRITE, at("src/deep/a.py"), p), Allow)
    assert isinstance(decide(WRITE, at("README.md"), p), Ask)


def test_dangerous_tools_ask_even_when_the_mode_allows() -> None:
    assert isinstance(decide(tool("shell", dangerous=True), CMD, policy("auto")), Ask)


def test_read_only_command_tools_count_as_reads() -> None:
    gh = tool("shell", name="gh_issue", kind="command", read_only=True)
    assert category(gh) == "read"
    assert isinstance(decide(gh, run("gh issue view 1"), policy("read-only")), Allow)


def test_control_files_ask_in_every_mode_but_yolo(tmp_path: Path) -> None:  # [PERM-12]
    cwd, home = tmp_path / "p", tmp_path / "h"
    is_control = control_files(cwd, home, ["AGENTS.md"])
    for path in [
        ".edgar/config.toml",
        "AGENTS.md",
        ".edgar/skills/x/SKILL.md",
        ".edgar/prompts/system.md",
    ]:
        s = Subject(str(cwd / path), path=(cwd / path).resolve())
        for mode in ("read-only", "ask", "auto"):
            p = Policy(
                mode=mode, cwd=cwd.resolve(), home=home, interactive=True, control=is_control
            )
            decision = decide(WRITE, s, p)
            assert isinstance(decision, Ask) and decision.source == "control", (path, mode)
    learned = (cwd / ".edgar/skills/learned/x/SKILL.md").resolve()
    assert not is_control(learned)
    assert is_control((home / ".edgar" / "config.toml").resolve())


def test_subjects_are_resolved_before_matching(tmp_path: Path) -> None:  # [PERM-5]
    (tmp_path / "root").mkdir()
    assert subject({"path": "src/../../x"}, tmp_path / "root").path == (tmp_path / "x").resolve()
    assert subject({"command": "ls"}, tmp_path).command == "ls"
    assert subject({"url": "https://a"}, tmp_path).text == "https://a"


def test_a_symlink_is_judged_by_where_it_lands(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link"
    try:
        link.symlink_to(tmp_path)
    except OSError:  # Windows without developer mode cannot create symlinks
        return
    s = subject({"path": "link/secret"}, root)
    p = Policy(mode="auto", cwd=root.resolve(), home=HOME, interactive=True)
    assert isinstance(decide(WRITE, s, p), Ask)


def test_segments() -> None:
    assert segments("a  b && c | d ;e\nf || g") == ["a b", "c", "d", "e", "f", "g"]


def test_within() -> None:
    assert within(ROOT / "a" / "b.py", ROOT, ["./**"])
    assert not within(Path("/elsewhere/b.py"), ROOT, ["./**"])
    tmp = Path("/tmp").resolve()
    assert within(tmp / "x", ROOT, [(tmp / "*").as_posix()])


_parts = st.lists(st.sampled_from(["..", ".", "src", "a", "..%2f", "/", "b.txt"]), max_size=6)


@given(parts=_parts, mode=st.sampled_from(["read-only", "ask", "auto"]))
def test_no_generated_path_writes_outside_the_root_unasked(parts: list[str], mode: str) -> None:
    path = (ROOT / "/".join(parts)).resolve() if parts else ROOT
    decision = decide(WRITE, Subject(str(path), path=path), policy(mode))
    if not path.is_relative_to(ROOT):
        assert not isinstance(decision, Allow)


@given(command=st.text(max_size=40), allow=st.lists(st.text(max_size=8), max_size=3))
def test_tainted_auto_never_runs_substitution_or_an_unlisted_command(
    command: str, allow: list[str]
) -> None:
    p = policy("auto", tainted=True, shell_allow=tuple(allow))
    decision = decide(SHELL, run(command), p)
    if isinstance(decision, Allow):
        assert segments(command) and "$(" not in command and "`" not in command


def test_once_grants_nothing_and_always_never_stores_a_control_file(tmp_path: Path) -> None:
    import asyncio

    from edgar.core.events import EventBus
    from edgar.permissions.guard import Answer, Guard
    from edgar.storage.db import Store

    answers: list[Answer] = ["once", "always"]

    async def asker(tool: str, subject: str, reason: str) -> Answer:
        return answers.pop(0)

    cwd = tmp_path.resolve()
    store = Store(cwd / "edgar.db")
    base = Policy(mode="ask", cwd=cwd, home=HOME, control=lambda p: p.name == "config.toml")
    guard = Guard(base, asker=asker, store=store)

    async def check(path: str) -> None:
        await guard.check(
            WRITE, {"path": path}, cwd=cwd, mode="ask", tainted=False, call_id="1", bus=EventBus()
        )

    asyncio.run(check("a.py"))
    assert guard.granted == set()
    asyncio.run(check("config.toml"))
    assert store.grants() == [] and len(guard.granted) == 1  # this session only
