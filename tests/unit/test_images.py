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
from edgar.tools.spill import spill, spill_image

PNG = (  # a 2x3 PNG: the eight-byte signature, then an IHDR saying 2 wide, 3 high
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x06\x00\x00\x00"
)
GIF = b"GIF89a" + (7).to_bytes(2, "little") + (5).to_bytes(2, "little") + b"\x00" * 8
# A start-of-frame segment is all `geometry` reads: precision, height, width.
JPEG = b"\xff\xd8\xff\xc0\x00\x11\x08" + (9).to_bytes(2) + (4).to_bytes(2) + b"\x03" * 10
WEBP = (
    b"RIFF\x00\x00\x00\x00WEBPVP8X"
    + b"\x00" * 8  # chunk size, then the flag byte and its three reserved bytes
    + (11).to_bytes(3, "little")  # width - 1
    + (13).to_bytes(3, "little")  # height - 1
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


# 2. The bytes go to a blob, never into the block or the record [ADR-0052].


@pytest.mark.parametrize(
    ("data", "kind", "size"),
    [
        (PNG, "image/png", (2, 3)),
        (GIF, "image/gif", (7, 5)),
        (JPEG, "image/jpeg", (4, 9)),
        (WEBP, "image/webp", (12, 14)),
    ],
)
def test_each_format_is_recognised_and_measured(
    data: bytes, kind: str, size: tuple[int, int], tmp_path: Path
) -> None:
    block = spill_image(data, blob_dir=tmp_path / "blobs", name="tu_1")
    assert block is not None
    assert (block.media_type, block.width, block.height) == (kind, *size)
    assert Path(block.ref).read_bytes() == data


def test_bytes_that_are_not_a_known_image_spill_nothing(tmp_path: Path) -> None:
    assert spill_image(b"not a picture at all", blob_dir=tmp_path / "blobs", name="x") is None
    assert not (tmp_path / "blobs").exists()


def test_a_truncated_header_is_unknown_geometry_not_a_crash(tmp_path: Path) -> None:
    block = spill_image(PNG[:12], blob_dir=tmp_path / "blobs", name="tu_2")
    assert block is not None and (block.width, block.height) == (0, 0)


def test_an_image_blob_lands_beside_the_spilled_text_under_the_same_rule(tmp_path: Path) -> None:
    # Same directory, same name sanitising, different suffix: one blob rule [CTX-13].
    blobs = tmp_path / "blobs"
    spill("x" * 4000, max_tokens=10, blob_dir=blobs, name="tu/3", root=tmp_path)
    block = spill_image(PNG, blob_dir=blobs, name="tu/3")
    assert block is not None
    assert sorted(p.name for p in blobs.iterdir()) == ["tu_3.png", "tu_3.txt"]
