"""Docs currency [NFR-10]: every public CLI subcommand and every top-level
config key is documented somewhere a first-week user would actually look.

Two surfaces, each read from the code that defines it so the test stays true
as the surface grows, the way `test_tour.py` reads the tour's own hooks:

- CLI subcommands come from `edgar.cli.admin.USAGE`, the same string argparse
  shows on a usage error — the literal command surface edgar itself claims.
- Config keys come from the top-level fields of `edgar.config.schema.Config`
  plus its v1 `LATER` keys (v2-only ones excluded; core/v2.md and ADR-0053
  agree v2 config is not a v1 doc obligation).

REPL slash commands are not checked here: `slash.COMMANDS` requires a help
string by construction (the `@command(name, help)` decorator), so `/help`
inside the REPL is already every slash command's own documentation.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import edgar.cli.admin as admin
import edgar.config.schema as schema

ROOT = Path(__file__).resolve().parents[2]

# Where a first-week user looks; docs/PRD.md is the exhaustive spec, not this
# tier, and is deliberately not one of them.
DOCS = [
    ROOT / "docs" / "COOKBOOK.md",
    ROOT / "docs" / "EXTENDING.md",
    ROOT / "docs" / "DEPENDENCIES.md",
    ROOT / "docs" / "FAQ.md",
    ROOT / "examples" / "README.md",
]
CORPUS = "\n".join(p.read_text(encoding="utf-8") for p in DOCS)

CONFIG_DOCS = [
    *DOCS,
    ROOT / "src" / "edgar" / "templates" / "config.toml",
    ROOT / "docs" / "PRD.md",
]
CONFIG_CORPUS = "\n".join(p.read_text(encoding="utf-8") for p in CONFIG_DOCS)

V2_ONLY_CONFIG_KEYS = {"model.fallback", "model.escalation", "controller", "history"}


def _cli_subcommands() -> list[str]:
    return sorted(set(re.findall(r"\bedgar (\w+)", admin.USAGE)))


def _config_keys() -> list[str]:
    sections = [f.name for f in fields(schema.Config) if f.name not in ("origins", "later")]
    later = sorted(schema.LATER - V2_ONLY_CONFIG_KEYS)
    return sorted(set(sections) | {k.split(".")[0] for k in later})


def test_every_cli_subcommand_is_documented() -> None:
    undocumented = [w for w in _cli_subcommands() if not re.search(rf"\b{w}\b", CORPUS)]
    assert undocumented == [], f"no doc under {[p.name for p in DOCS]} mentions: {undocumented}"


def test_every_v1_config_key_is_documented() -> None:
    undocumented = [
        w for w in _config_keys() if not re.search(rf"\`?\[?{w}\b|\`{w}\.", CONFIG_CORPUS)
    ]
    assert undocumented == [], f"no doc mentions the config key: {undocumented}"
