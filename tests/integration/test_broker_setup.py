"""`begin()` attaches the receipt log through the same seam as `--scope`, and
`[broker] enabled = false` turns both the veto and the receipt off [ADR-0039].
"""

from __future__ import annotations

from pathlib import Path

from edgar.cli.setup import Setup, begin, setup
from edgar.config.schema import BrokerSection, Config, ModelSection
from edgar.core.events import EventBus, PromptTyped


def _setup(root: Path, home: Path, *, enabled: bool = True) -> Setup:
    config = Config(model=ModelSection(default="fake/test"), broker=BrokerSection(enabled=enabled))
    return setup(root, config, home=home, env={})


def test_begin_writes_a_receipt_when_the_broker_is_enabled(tmp_project: Path, home: Path) -> None:
    bus = EventBus()
    session, _ = begin(_setup(tmp_project, home), bus)
    bus.emit(PromptTyped(text="do the thing"))
    assert (session.dir / "receipt.jsonl").exists()


def test_broker_enabled_false_writes_no_receipt(tmp_project: Path, home: Path) -> None:
    bus = EventBus()
    session, _ = begin(_setup(tmp_project, home, enabled=False), bus)
    bus.emit(PromptTyped(text="do the thing"))
    assert not (session.dir / "receipt.jsonl").exists()
