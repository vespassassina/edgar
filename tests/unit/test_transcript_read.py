"""Reading a JSONL record after a crash [ADR-0010, BLUEPRINT §3.4].

A write is one line with its newline, so a crash mid-write can leave at most
the last line torn: text with no newline yet. The reader drops that line and
keeps the rest; a bad line anywhere else is real damage and still raises.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar.storage.transcript import entries


def test_a_complete_record_reads_every_line(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "a"}\n{"type": "b"}\n', encoding="utf-8")
    assert [e["type"] for e in entries(path)] == ["a", "b"]


def test_a_torn_last_line_is_dropped_and_the_rest_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "a"}\n{"type": "b"}\n{"type": "c", "te', encoding="utf-8")
    assert [e["type"] for e in entries(path)] == ["a", "b"]


def test_a_bad_line_in_the_middle_still_raises(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text('{"type": "a"}\nnot json\n{"type": "b"}\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        entries(path)
