"""Generate the tour's map of the harness: docs/tour/map.json and map.data.js.

Run it with `just map`. The JSON is committed, and tests/unit/test_tour_map.py
regenerates it in memory and fails if the committed copy has drifted, so the map
cannot quietly describe a tree that no longer exists.

map.data.js holds the same object as `window.EDGAR_MAP`, because map.html has to
work opened as a local file and `fetch("map.json")` does not, under file://.
"""

# What this does, in order:
#
#   1. read every stop on every tour page: which file it names, and whether it is planned
#   2. walk src/edgar for .py files; add the files that only a planned stop names
#   3. for each file work out its tier, package, size, one-line summary, stop and port
#   4. nest them: root -> tier -> package -> file, sizes adding up on the way out
#   5. write map.json and map.data.js, byte for byte the same every run
#
# Everything is sorted before it is written, so a regeneration is reproducible.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "edgar"
TOUR = ROOT / "docs" / "tour"

sys.path.insert(0, str(ROOT / "tests" / "support"))
from budget import count_loc  # noqa: E402  (the one counter: never reimplement it)

# The same regex the tour's own test uses. The pages are ours and the hooks are fixed.
STOP = r'<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">'

# Which milestone first shipped a file. Hand-maintained, and derived from the tour
# itself: everything Part I of index.html names is Core, so what is listed here is what
# arrived with v1. A file under one of these prefixes, or named outright, is v1; the
# planned paths are v3 and v4; anything else is Core.
V1_PREFIXES = ("agents/", "auth/", "extensions/", "memory/", "tools/mcp/")
V1_FILES = (
    "__init__.py",
    "cli/doctor.py",
    "cli/init.py",
    "cli/memory.py",
    "providers/fallback.py",
    "skills/activate.py",
    "tools/builtin/memory_tools.py",
    "tools/builtin/task.py",
    "tools/builtin/tool_search.py",
)
# v2 extends Core and v1 in their own packages, so it is a list of files, never a
# prefix: a new v2 module has to be named here or it is reported as Core (M19).
V2_FILES = (
    "cli/inspect.py",
    "context/attach.py",
    "context/working.py",
    "tools/builtin/todo.py",
)
V3_PREFIXES = ("controller/", "learning/")
V3_FILES = ("providers/escalation.py",)
V4_PREFIXES = ("broker/", "schedule/")

TIERS = (
    ("core", "Core", "M0 to M6", "The smallest honest harness."),
    ("v1", "v1", "M7 to M11", "Extensible, and it remembers."),
    ("v2", "v2, the daily driver", "M18 to M22", "Liveable. Not removable."),
    ("v3", "v3, learning", "M12 to M15", "Learns from verified work. Removable."),
    ("v4", "v4, unattended", "M17 then M16", "Runs while you are away. Removable."),
)

# ADR-0022's six ports. sandbox/base.py has no file yet, so it has no node.
PORTS = (
    "cli/render.py",
    "memory/retriever.py",
    "providers/base.py",
    "sandbox/base.py",
    "skills/discovery.py",
    "tools/base.py",
)


def stops_by_file() -> dict[str, tuple[str, bool]]:
    # 1. Every stop on every page, as file -> (page#id, is it a planned stop).
    #    A file named by more than one stop belongs to the page that is about it, so a
    #    feature page wins over index.html; otherwise the first in page then id order.
    found: dict[str, list[tuple[int, str, bool]]] = {}
    for page in sorted(TOUR.glob("*.html")):
        for match in re.finditer(STOP, page.read_text(encoding="utf-8")):
            planned = bool(match[1])
            rank = 1 if page.name == "index.html" else 0
            for path in match[3].split():
                found.setdefault(path, []).append((rank, f"{page.name}#{match[2]}", planned))
    return {path: (best[1], best[2]) for path, hits in found.items() if (best := min(hits))}


def summary_of(path: Path) -> str:
    # 2. The first line of the file's opening comment block, or of its docstring,
    #    whichever comes first. Several files have neither, and get an empty summary.
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped.startswith(('"""', "'''")):
            return stripped[3:].removesuffix('"""').removesuffix("'''").strip()
        return ""
    return ""


def tier_of(rel: str) -> str:
    # 3. The milestone that first shipped this file, by the table above.
    if rel.startswith(V1_PREFIXES) or rel in V1_FILES:
        return "v1"
    if rel in V2_FILES:
        return "v2"
    if rel.startswith(V3_PREFIXES) or rel in V3_FILES:
        return "v3"
    if rel.startswith(V4_PREFIXES):
        return "v4"
    return "core"


def package_of(rel: str) -> str:
    # 4. The package a file sits in: "tools/mcp" for tools/mcp/client.py, "edgar" for
    #    a file directly under src/edgar.
    parent = str(Path(rel).parent).replace("\\", "/")
    return "edgar" if parent == "." else parent


def file_nodes() -> list[dict[str, Any]]:
    # 5. One node per file: what is on disk, plus the files only a planned stop names.
    #    A package's empty __init__.py is not a node: it would be a leaf with nothing to
    #    say. edgar's own is not empty and is kept.
    stops = stops_by_file()
    paths = {
        f.relative_to(ROOT).as_posix()
        for f in SRC.rglob("*.py")
        if f.name != "__init__.py" or f.parent == SRC
    }
    paths.update(path for path, (_, planned) in stops.items() if planned)
    nodes = []
    for path in sorted(paths):
        full = ROOT / path
        rel = path.removeprefix("src/edgar/")
        stop, _planned = stops.get(path, (None, False))
        nodes.append(
            {
                "path": path,
                "name": Path(path).name,
                "kind": "file",
                "tier": tier_of(rel),
                "package": package_of(rel),
                "loc": count_loc(full) if full.exists() else 0,
                "summary": summary_of(full) if full.exists() else "",
                "stop": stop,
                "status": "planned" if not full.exists() else "built",
                "port": rel in PORTS,
            }
        )
    return nodes


def build_map() -> dict[str, Any]:
    # 6. Nest the files under their package, the packages under their tier, and add the
    #    sizes up on the way out. The root is the whole of src/edgar.
    files = file_nodes()
    tiers = []
    for key, name, milestones, blurb in TIERS:
        mine = [f for f in files if f["tier"] == key]
        packages = []
        for package in sorted({str(f["package"]) for f in mine}):
            kids = [f for f in mine if f["package"] == package]
            packages.append(
                {
                    "id": f"{key}/{package}",
                    "name": f"{package}/",
                    "kind": "package",
                    "loc": sum(int(f["loc"]) for f in kids),
                    "status": "built" if any(f["status"] == "built" for f in kids) else "planned",
                    "children": kids,
                }
            )
        tiers.append(
            {
                "id": key,
                "name": name,
                "kind": "tier",
                "milestones": milestones,
                "summary": blurb,
                "loc": sum(int(p["loc"]) for p in packages),
                "status": "built" if any(p["status"] == "built" for p in packages) else "planned",
                "children": packages,
            }
        )
    return {
        "generated_by": "scripts/tour_map.py",
        "note": "Generated. Run `just map` after changing src/edgar or a tour stop.",
        "root": {
            "id": "edgar",
            "name": "src/edgar",
            "kind": "root",
            "loc": sum(int(t["loc"]) for t in tiers),
            "status": "built",
            "children": tiers,
        },
    }


def as_json(data: dict[str, Any]) -> str:
    # 7. One shape for both files, so the regeneration test can compare bytes.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def as_js(data: dict[str, Any]) -> str:
    head = "// Generated by scripts/tour_map.py. map.html reads this, not map.json:\n"
    head += "// fetch() cannot read a sibling file when the page is opened as file://\n"
    return head + "window.EDGAR_MAP = " + as_json(data).rstrip("\n") + ";\n"


def main() -> int:
    data = build_map()
    (TOUR / "map.json").write_text(as_json(data), encoding="utf-8")
    (TOUR / "map.data.js").write_text(as_js(data), encoding="utf-8")
    files = [f for t in data["root"]["children"] for p in t["children"] for f in p["children"]]
    orphans = [f["path"] for f in files if f["stop"] is None]
    print(f"map.json: {len(files)} files, {data['root']['loc']} lines of code")
    print(f"no stop names: {orphans}" if orphans else "every file has a stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
