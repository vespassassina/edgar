"""The tour's map (docs/tour/map.json) is generated, and stays that way.

Regenerate it in memory with the same function `just map` calls, and fail if a byte
of the committed copy differs. A file added to src/edgar, a stop moved to another
page or a size changed all show up here, and the fix is always `just map`.
"""

from __future__ import annotations

import importlib.util
from types import ModuleType

from budget import SRC

ROOT = SRC.parents[1]
GENERATOR = ROOT / "scripts" / "tour_map.py"
TOUR = ROOT / "docs" / "tour"


def _generator() -> ModuleType:
    # Loaded by path: scripts/ is not a package, and nothing else imports it.
    spec = importlib.util.spec_from_file_location("tour_map", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_map_is_what_the_generator_writes() -> None:
    generator = _generator()
    data = generator.build_map()
    for name, rendered in (
        ("map.json", generator.as_json(data)),
        ("map.data.js", generator.as_js(data)),
    ):
        committed = (TOUR / name).read_text(encoding="utf-8")
        assert committed == rendered, f"docs/tour/{name} is out of date: run `just map`"


def test_every_file_in_the_map_has_a_stop_and_a_tier() -> None:
    # The map is only useful if each node leads somewhere. A planned file has a planned
    # stop; a built one has a built stop; neither may have none.
    data = _generator().build_map()
    files = [f for t in data["root"]["children"] for p in t["children"] for f in p["children"]]
    assert len(files) > 80
    assert not [f["path"] for f in files if f["stop"] is None]
    assert not [f["path"] for f in files if f["tier"] not in {"core", "v1", "v3", "v4"}]
