"""The tour (docs/tour/*.html) stays true to the code [ADR-0040].

It fails when a linked file is gone, when a name under "Look for" is no longer
defined in its stop's files, when a package's size in the table drifts more than
100 lines of code, when a package has no row, when a file's own size on a feature
page drifts more than 25, when a planned file has landed while its stop still says
planned, or when the turn diagram's steps stop matching the loop's numbered
comments. It cannot tell when a description has gone stale.
"""

# How the pages are read. Every tour page is hand-written HTML with a few fixed
# hooks, the same on all of them since M18:
#
#   <article class="stop" id="s1" data-files="src/edgar/a.py ...">   a built stop
#   <article class="stop planned" id="s19" data-files="...">         files not written yet
#   <p class="look">Look for: <code>name</code> ...</p>               names its files define
#   <tr data-package="core"> ... <td class="loc">~700</td>           index's size table
#   <tr data-file="src/edgar/a.py"> ... <td class="loc">~120</td>    a feature page's
#   <a href="https://github.com/vespassassina/edgar/blob/main/PATH"><code>TEXT</code></a>
#
# Regular expressions are enough because the pages are ours and the hooks are fixed.

from __future__ import annotations

import re
from pathlib import Path

import pytest
from budget import SRC, count_loc

ROOT = SRC.parents[1]
TOUR = ROOT / "docs" / "tour"
PAGES = {p.name: p.read_text(encoding="utf-8") for p in sorted(TOUR.glob("*.html"))}
PAGE = PAGES["index.html"]
BLOB = "https://github.com/vespassassina/edgar/blob/main/"

STOP = re.compile(
    r'<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">(.*?)</article>', re.S
)
LOOK = re.compile(r'<p class="look">(.*?)</p>', re.S)
CODE = re.compile(r"<code>([^<]+)</code>")
LINK = re.compile(r'<a href="' + re.escape(BLOB) + r'([^"#]+)[^"]*">(.*?)</a>', re.S)
ROW = re.compile(r'<tr data-package="(\w+)">.*?<td class="loc">~([\d,]+)</td>', re.S)
FILEROW = re.compile(r'<tr data-file="([^"]+)">.*?<td class="loc">~([\d,]+)</td>', re.S)
TOLERANCE = 100  # lines of code a rounded package size may drift before the table is wrong
FILE_TOLERANCE = 25  # a single file's rounded size is quoted more tightly


def _stops(*, planned: bool) -> list[tuple[str, list[Path], str]]:
    # Every stop of one kind on every page, as (page#id, its files, its inner HTML).
    found = []
    for page, text in PAGES.items():
        for match in STOP.finditer(text):
            if bool(match[1]) == planned:
                files = [ROOT / path for path in match[3].split()]
                found.append((f"{page}#{match[2]}", files, match[4]))
    return found


def _defines(files: list[Path], name: str) -> bool:
    # Does any of these Python files define `name`: def, async def, class, or NAME = ?
    pattern = re.compile(rf"^\s*(?:async def|def|class) {name}\b|^\s*{name}\s*[:=]", re.M)
    sources = (f.read_text(encoding="utf-8") for f in files if f.suffix == ".py")
    return any(pattern.search(source) for source in sources)


def covered_files() -> set[str]:
    # Every src path any stop on any page claims, as a repo-relative posix string.
    claimed: set[str] = set()
    for text in PAGES.values():
        for match in STOP.finditer(text):
            claimed.update(match[3].split())
    return claimed


BUILT = _stops(planned=False)
PLANNED = _stops(planned=True)


def test_the_pages_have_their_stops() -> None:
    # A regex that silently matches nothing would pass every test below.
    assert len(BUILT) >= 18
    assert PLANNED
    assert len(PAGES) >= 1


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


@pytest.mark.parametrize("page", sorted(PAGES), ids=sorted(PAGES))
def test_every_link_to_the_repository_resolves(page: str) -> None:
    # A link's path exists, and a link shown as a path is the path it points to.
    for path, text in LINK.findall(PAGES[page]):
        assert (ROOT / path).exists(), f"{page}: broken link: {path}"
        shown = CODE.fullmatch(text)
        assert shown is None or path.endswith(shown[1]), f"{page}: {shown[1]} links to {path}"


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


@pytest.mark.parametrize("page", sorted(PAGES), ids=sorted(PAGES))
def test_a_per_file_size_row_matches_its_file(page: str) -> None:
    # A feature page quotes one file per row, so it is held to a tighter drift.
    for path, size in FILEROW.findall(PAGES[page]):
        target = ROOT / path
        assert target.exists(), f"{page}: size row for a file that is gone: {path}"
        drift = abs(count_loc(target) - int(size.replace(",", "")))
        assert drift <= FILE_TOLERANCE, f"{page}: {path} says ~{size}, code has {count_loc(target)}"


def test_the_turn_diagram_follows_the_loop() -> None:
    # Each numbered step in the turn diagram ("1 · record the prompt") is a numbered
    # comment in run_turn ("# 1. Record the prompt").
    diagram = next(body for stop, _, body in BUILT if stop == "index.html#s1")
    steps = re.findall(r'"(\d+) · ', diagram)
    loop = (SRC / "core" / "loop.py").read_text(encoding="utf-8")
    assert steps
    for step in steps:
        assert f"# {step}. " in loop, f"step {step} is in the diagram but not in loop.py"


@pytest.mark.parametrize("page", sorted(PAGES), ids=sorted(PAGES))
def test_the_page_loads_its_own_files(page: str) -> None:
    # Every relative href or src (tour.css, tour.js, the vendored artifactkit) is on disk.
    for ref in re.findall(r'(?:href|src)="(?!https?:|#|data:)([^"]+)"', PAGES[page]):
        assert (TOUR / ref).exists(), f"{page}: missing next to the page: {ref}"


@pytest.mark.parametrize("page", sorted(PAGES), ids=sorted(PAGES))
def test_no_diagram_label_reads_as_a_list(page: str) -> None:
    # Mermaid renders a label that opens with "1. " as a Markdown list, which it cannot
    # draw: the node shows "Unsupported markdown: list". Write "1 · " instead.
    diagrams = re.findall(r'<pre class="mermaid">(.*?)</pre>', PAGES[page], re.S)
    for diagram in diagrams:
        assert not re.search(r'"\d+[.)] ', diagram), f"{page}: a label opens like a list"
