"""Images: the block, the spill, the capability gate, counting and elision [ADR-0052].

One file for the whole of M20's image path, in the order the roadmap builds it, so
a reader sees the block, where its bytes live and what every stage does with it
without opening six test files.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from edgar.core.message import ImageBlock, Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.units import pairing_violations
from edgar.storage.transcript import from_dict, to_dict

PNG = (  # a 2x3 PNG: the eight-byte signature, then an IHDR saying 2 wide, 3 high
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x06\x00\x00\x00"
)


def unit_with_an_image(ref: str = "blobs/tu_1.png") -> list[Message]:
    # One tool exchange whose result carries a picture: the shape every stage must
    # survive without breaking the pairing invariant [CTX-4].
    call = Message("assistant", (ToolUseBlock("tu_1", "read", {"path": "shot.png"}),))
    image = ImageBlock("image/png", ref, 2, 3)
    result = ToolResultBlock("tu_1", (TextBlock("shot.png: PNG 2x3"),), images=(image,))
    return [Message.user("what is in @shot.png"), call, Message("tool", (result,))]


def test_an_image_block_is_frozen_like_every_other_block() -> None:
    block = ImageBlock("image/png", "blobs/a.png", 2, 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.ref = "elsewhere"  # type: ignore[misc]  # the point of the test


def test_dimensions_default_to_zero_when_the_header_could_not_be_read() -> None:
    assert (ImageBlock("image/png", "blobs/a.png").width, ImageBlock("x", "y").height) == (0, 0)


def test_a_unit_carrying_an_image_still_satisfies_the_pairing_invariant() -> None:
    assert pairing_violations(unit_with_an_image()) == []


def test_a_message_lists_its_own_images_and_its_results_images() -> None:
    view = unit_with_an_image()
    typed = Message("user", (TextBlock("look"), ImageBlock("image/png", "blobs/a.png")))
    assert [i.ref for i in typed.images] == ["blobs/a.png"]
    assert [i.ref for i in view[2].images] == ["blobs/tu_1.png"]
    assert view[1].images == ()


def test_an_image_round_trips_through_the_session_record() -> None:
    # JSONL carries the reference, never the bytes [ADR-0052].
    for message in (unit_with_an_image()[2], Message("user", (ImageBlock("image/png", "a.png"),))):
        line = to_dict(message)
        assert "base64" not in repr(line)
        assert from_dict(line) == message


def test_a_result_written_before_m20_still_reads_back(tmp_path: Path) -> None:
    # No "images" key at all: every session recorded before this milestone.
    old = {
        "role": "tool",
        "content": [
            {
                "kind": "ToolResultBlock",
                "tool_use_id": "tu_1",
                "content": [{"text": "ok", "attached": False}],
                "is_error": False,
                "truncated": False,
                "untrusted": False,
                "error": None,
                "blob": None,
            }
        ],
        "meta": {},
    }
    assert from_dict(old).tool_results[0].images == ()
