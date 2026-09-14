"""The tour (docs/tour/index.html) stays true to the code [ADR-0040].

It fails when a linked file is gone, when a name under "Look for" is no longer
defined in its stop's files, when a package's size in the table drifts more than
100 lines of code, when a package has no row, when a planned file has landed while
its stop still says planned, or when the turn diagram's steps stop matching the
loop's numbered comments. It cannot tell when a description has gone stale.
"""

# How the page is read. The tour is hand-written HTML with a few fixed hooks:
#
#   <article class="stop" id="s1" data-files="src/edgar/a.py ...">   a built stop
#   <article class="stop planned" id="s19" data-files="...">         files not written yet
#   <p class="look">Look for: <code>name</code> ...</p>               names its files define
#   <tr data-package="core"> ... <td class="loc">~700</td>           the size table
#   <a href="https://github.com/vespassassina/edgar/blob/main/PATH"><code>TEXT</code></a>
#
# Regular expressions are enough because the page is ours and the hooks are fixed.

from __future__ import annotations

import re
from pathlib import Path

import pytest
from budget import SRC, count_loc

ROOT = SRC.parents[1]
PAGE = (ROOT / "docs" / "tour" / "index.html").read_text(encoding="utf-8")
BLOB = "https://github.com/vespassassina/edgar/blob/main/"

STOP = re.compile(
    r'<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">(.*?)</article>', re.S
)
LOOK = re.compile(r'<p class="look">(.*?)</p>', re.S)
CODE = re.compile(r"<code>([^<]+)</code>")
LINK = re.compile(r'<a href="' + re.escape(BLOB) + r'([^"#]+)[^"]*">(.*?)</a>', re.S)
ROW = re.compile(r'<tr data-package="(\w+)">.*?<td class="loc">~([\d,]+)</td>', re.S)
TOLERANCE = 100  # lines of code a rounded size may drift before the table is wrong


def _stops(*, planned: bool) -> list[tuple[str, list[Path], str]]:
    # Every stop of one kind, as (id, its files, its inner HTML).
    found = []
    for match in STOP.finditer(PAGE):
        if bool(match[1]) == planned:
            files = [ROOT / path for path in match[3].split()]
            found.append((match[2], files, match[4]))
    return found


def _defines(files: list[Path], name: str) -> bool:
    # Does any of these Python files define `name`: def, async def, class, or NAME = ?
    pattern = re.compile(rf"^\s*(?:async def|def|class) {name}\b|^\s*{name}\s*[:=]", re.M)
    sources = (f.read_text(encoding="utf-8") for f in files if f.suffix == ".py")
    return any(pattern.search(source) for source in sources)


BUILT = _stops(planned=False)
PLANNED = _stops(planned=True)


def test_the_page_has_its_stops() -> None:
    # A regex that silently matches nothing would pass every test below.
    assert len(BUILT) >= 18
    assert PLANNED


@pytest.mark.parametrize(("stop", "files", "body"), BUILT, ids=[s[0] for s in BUILT])
def test_a_built_stop_names_real_code(stop: str, files: list[Path], body: str) -> None:
    # 1. Every file the stop covers exists.
    missing = [str(f.relative_to(ROOT)) for f in files if not f.exists()]
    assert not missing, f"{stop}: files gone: {missing}"
    # 2. Every name under "Look for" is defined in one of them.
    look = LOOK.search(body)
    assert look, f"{stop}: no Look for line"
    names = CODE.findall(look[1])
    undefined = [name for name in names if not _defines(files, name)]
    assert not undefined, f"{stop}: not defined in its files: {undefined}"


@pytest.mark.parametrize(("stop", "files", "body"), PLANNED, ids=[s[0] for s in PLANNED])
def test_a_planned_stop_is_still_planned(stop: str, files: list[Path], body: str) -> None:
    # A planned file that now exists means its milestone landed: link the stop.
    landed = [str(f.relative_to(ROOT)) for f in files if f.exists()]
    assert not landed, f"{stop}: landed, make it a built stop with links: {landed}"


def test_every_link_to_the_repository_resolves() -> None:
    # A link's path exists, and a link shown as a path is the path it points to.
    for path, text in LINK.findall(PAGE):
        assert (ROOT / path).exists(), f"broken link: {path}"
        shown = CODE.fullmatch(text)
        assert shown is None or path.endswith(shown[1]), f"{shown[1]} links to {path}"


def test_the_size_table_matches_the_code() -> None:
    # 1. The table as written: package -> rounded lines of code.
    table = {package: int(size.replace(",", "")) for package, size in ROW.findall(PAGE)}
    # 2. The code as it is: every package directory that holds Python.
    packages = sorted(d.name for d in SRC.iterdir() if d.is_dir() and any(d.rglob("*.py")))
    for package in packages:
        assert package in table, f"{package}/ has no row in the size table"
        actual = sum(count_loc(f) for f in (SRC / package).rglob("*.py"))
        drift = abs(actual - table[package])
        assert drift <= TOLERANCE, f"{package}/: table says ~{table[package]}, code has {actual}"


def test_the_turn_diagram_follows_the_loop() -> None:
    # Each numbered step in the turn diagram is a numbered comment in run_turn.
    diagram = next(body for stop, _, body in BUILT if stop == "s1")
    steps = re.findall(r'"(\d+)\. ', diagram)
    loop = (SRC / "core" / "loop.py").read_text(encoding="utf-8")
    assert steps
    for step in steps:
        assert f"# {step}. " in loop, f"step {step} is in the diagram but not in loop.py"
