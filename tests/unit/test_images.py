"""Images: the block, the spill, the capability gate, counting and elision [ADR-0052].

One file for the whole of M20's image path, in the order the roadmap builds it, so
a reader sees the block, where its bytes live and what every stage does with it
without opening six test files.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from edgar.config.schema import ProviderSection
from edgar.context.compact import elide
from edgar.context.tokens import approx_message_tokens, image_tokens
from edgar.core.errors import ConfigError
from edgar.core.message import ImageBlock, Message, TextBlock, ToolResultBlock, ToolUseBlock
from edgar.core.units import pairing_violations
from edgar.providers.quirks import QUIRKS, quirks_for
from edgar.providers.routing import check_images
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


# 3. A model that cannot see refuses where it is chosen, never mid-turn [ROUTE-6].


def test_a_provider_without_images_is_refused_by_name() -> None:
    with pytest.raises(ConfigError) as raised:
        check_images("ollama/qwen3:8b", has_images=False)
    assert "cannot take images" in str(raised.value)
    assert raised.value.hint and "images = true" in raised.value.hint


def test_a_provider_with_images_passes_quietly() -> None:
    check_images("openai/gpt-5", has_images=True)  # no exception is the whole assertion


@pytest.mark.parametrize("name", ["openai", "azure", "openrouter", "anthropic"])
def test_the_cloud_rows_take_images(name: str) -> None:
    assert QUIRKS[name].images


def test_a_server_edgar_knows_nothing_about_does_not_claim_to_see() -> None:
    # The conservative default, like every other quirk of an unknown server [PRV-12].
    assert not QUIRKS["ollama"].images
    assert not quirks_for("mine", ProviderSection(base_url="http://localhost:1234/v1")).images
    stated = ProviderSection(base_url="http://localhost:1234/v1", images=True)
    assert quirks_for("mine", stated).images


# 4. What a picture costs: geometry, per family, as a pure function [ADR-0052].


def test_a_small_image_costs_one_tile_on_chat_completions() -> None:
    assert image_tokens(ImageBlock("image/png", "b.png", 100, 100)) == 85 + 170


def test_a_wide_image_costs_a_tile_per_512_pixels() -> None:
    # 1024x512 covers two tiles across and one down.
    assert image_tokens(ImageBlock("image/png", "b.png", 1024, 512)) == 85 + 2 * 170


def test_an_oversized_image_is_shrunk_before_it_is_tiled() -> None:
    # 4096x4096 fits the 2048 square, then its short side down to 768: 2x2 tiles.
    assert image_tokens(ImageBlock("image/png", "b.png", 4096, 4096)) == 85 + 4 * 170


def test_anthropic_charges_by_area_not_by_tiles() -> None:
    block = ImageBlock("image/png", "b.png", 750, 1000)
    assert image_tokens(block, "anthropic") == 1000  # 750 * 1000 / 750


def test_an_unmeasured_image_costs_one_tile_rather_than_nothing() -> None:
    # A header the spill could not read leaves 0x0; charging nothing would let a
    # session drift over the window with no warning [CTX-3].
    assert image_tokens(ImageBlock("image/png", "b.png")) == 85 + 170


def test_counting_a_message_includes_its_images() -> None:
    shot = ImageBlock("image/png", "b.png", 100, 100)
    plain = [Message("user", (TextBlock("look"),))]
    withimage = [Message("user", (TextBlock("look"), shot))]
    assert approx_message_tokens(withimage) - approx_message_tokens(plain) == 85 + 170


def test_counting_a_message_includes_an_image_a_tool_produced() -> None:
    shot = ImageBlock("image/png", "b.png", 100, 100)
    result = ToolResultBlock("tu_1", (TextBlock("read"),), images=(shot,))
    counted = approx_message_tokens([Message("tool", (result,))])
    assert counted > 85 + 170


# 5. S1 elides an old picture to a line naming it [CTX-4, CTX-11, ADR-0052].


def test_an_old_image_elides_to_a_line_that_keeps_its_reference() -> None:
    view = [
        Message("user", (TextBlock("look"), ImageBlock("image/png", "blobs/a.png", 640, 480))),
        Message("assistant", (TextBlock("I see"),)),
        Message.user("and now?"),
    ]
    out = elide(view, 2)
    assert out[0].images == ()  # nothing left to pay for
    said = out[0].content[1]
    assert isinstance(said, TextBlock)
    assert "image/png 640x480" in said.text and "blobs/a.png" in said.text


def test_an_image_a_tool_produced_elides_with_its_result() -> None:
    view = [*unit_with_an_image("blobs/shot.png"), Message.user("next")]
    out = elide(view, 3)
    assert pairing_violations(out) == []  # the unit stayed whole [CTX-4]
    assert out[2].images == ()
    assert "image blobs/shot.png" in out[2].tool_results[0].text


def test_eliding_an_image_twice_changes_nothing_more() -> None:
    view = [*unit_with_an_image(), Message.user("next")]
    once = elide(view, 3)
    assert elide(once, 3) == once


def test_the_recent_turn_keeps_its_images() -> None:
    shot = ImageBlock("image/png", "blobs/a.png", 640, 480)
    view = [Message("user", (TextBlock("look"), shot))]
    assert elide(view, 0) == view  # nothing before the cut: nothing to elide
