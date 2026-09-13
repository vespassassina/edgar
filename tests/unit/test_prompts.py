"""The prompt is a file, and it has a budget [CTX-16, NFR-13]."""

from __future__ import annotations

import json
from pathlib import Path

from edgar.context.prompts import SHIPPED, load_prompt
from edgar.context.tokens import approx_tokens
from edgar.tools.registry import core_registry


def test_prompt_budget() -> None:
    assert approx_tokens((SHIPPED / "system.md").read_text(encoding="utf-8")) <= 1_500
    schemas = [
        {"name": s.name, "description": s.description, "input_schema": s.input_schema}
        for s in core_registry().schemas()
    ]
    assert approx_tokens(json.dumps(schemas)) <= 2_500


def test_shipped_prompt_by_default(tmp_project: Path) -> None:
    prompt = load_prompt(tmp_project)
    assert prompt.source == SHIPPED / "system.md"
    assert "edgar" in prompt.text


def test_a_project_prompt_replaces_the_shipped_one(tmp_project: Path) -> None:
    own = tmp_project / ".edgar" / "prompts" / "system.md"
    own.parent.mkdir(parents=True)
    own.write_text("Be brief.", encoding="utf-8")
    assert load_prompt(tmp_project).text == "Be brief."


def test_no_volatile_values_in_the_shipped_prompt() -> None:
    # Anything that changes between requests would break the cached prefix [CTX-17].
    text = (SHIPPED / "system.md").read_text(encoding="utf-8")
    assert "{" not in text and "$" not in text
