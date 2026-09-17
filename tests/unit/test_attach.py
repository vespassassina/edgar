"""`@path` attaches a file's text to the user message [CLI-3, MEM-9]."""

from __future__ import annotations

import asyncio
from pathlib import Path

from harness import new_session, runtime, scripted, texts

from edgar.context.attach import Attached, attach
from edgar.core.loop import run_turn
from edgar.core.message import TextBlock


def _attach(prompt: str, cwd: Path, max_tokens: int = 8000) -> Attached:
    return attach(
        prompt,
        cwd=cwd,
        home=cwd.parent / "home",
        max_tokens=max_tokens,
        blob_dir=cwd / ".edgar" / "blobs",
    )


def test_an_at_path_becomes_one_attached_block_on_the_user_message(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("the readme body", encoding="utf-8")
    found = _attach("summarise @README.md please", tmp_path)
    assert not found.problems
    session = new_session(tmp_path)
    rt = runtime(scripted(*texts(["done"])))
    asyncio.run(run_turn(session, "summarise @README.md please", rt, attached=found.bodies))

    users = [m for m in session.transcript if m.role == "user"]
    assert len(users) == 1
    blocks = [b for b in users[0].content if isinstance(b, TextBlock)]
    # What the human typed is one block, unchanged and not attached: only that block
    # may ever reach the learning path [MEM-9].
    assert blocks[0].text == "summarise @README.md please"
    assert not blocks[0].attached
    attached = [b for b in blocks if b.attached]
    assert len(attached) == 1
    assert "the readme body" in attached[0].text
    assert "README.md" in attached[0].text


def test_a_missing_path_is_a_message_not_an_exception(tmp_path: Path) -> None:
    found = _attach("look at @missing/path", tmp_path)
    assert not found.bodies
    assert len(found.problems) == 1
    assert "@missing/path" in found.problems[0]
    assert "text file" in found.problems[0]


def test_a_control_file_attaches_because_reading_one_is_allowed(tmp_path: Path) -> None:
    # policy.py asks about a control file only when a tool would *write* it; a read
    # inside the working directory is allowed in every mode, so attaching one is too.
    config = tmp_path / ".edgar" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[model]\ndefault = "fake/test"\n', encoding="utf-8")
    found = _attach("what does @.edgar/config.toml say?", tmp_path)
    assert not found.problems
    assert 'default = "fake/test"' in found.bodies[0]


def test_a_directory_and_a_binary_file_are_refused_by_name(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "a.bin").write_bytes(b"\x00\x01\x02\xff\xfe")  # not text, not a picture
    found = _attach("read @docs and @a.bin", tmp_path)
    assert not found.bodies
    assert any("@docs is a directory" in p for p in found.problems)
    assert any("@a.bin" in p for p in found.problems)


def test_a_path_outside_the_working_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere.txt"
    outside.write_text("secrets", encoding="utf-8")
    found = _attach(f"read @../{outside.name}", tmp_path)
    assert not found.bodies
    assert "outside the working directory" in found.problems[0]


def test_an_oversized_attachment_spills_like_tool_output(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * 20_000, encoding="utf-8")
    found = _attach("@big.txt", tmp_path, max_tokens=100)
    assert "characters omitted" in found.bodies[0]
    assert (tmp_path / ".edgar" / "blobs" / "attach_0.txt").read_text(encoding="utf-8") == (
        "x" * 20_000
    )


def test_an_email_address_is_not_an_attachment(tmp_path: Path) -> None:
    # The token has to start a word, so "write to a@b.com" attaches nothing.
    assert _attach("write to a@b.com", tmp_path).problems == ()


def test_an_at_path_to_a_picture_attaches_it_as_an_image(tmp_path: Path) -> None:
    # A PNG used to be refused as "not a text file"; from M20 it is the point [ADR-0052].
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x06\x00\x00\x00"
    (tmp_path / "shot.png").write_bytes(png)
    found = _attach("what is in @shot.png", tmp_path)
    assert not found.problems and not found.bodies
    (shot,) = found.images
    assert (shot.media_type, shot.width, shot.height) == ("image/png", 2, 3)
    assert Path(shot.ref).read_bytes() == png  # the bytes went to the blobs, not the prompt


def test_a_picture_outside_the_working_directory_is_still_refused(tmp_path: Path) -> None:
    # The refusal rules are the same for a picture as for text [CLI-3].
    outside = tmp_path.parent / "elsewhere.png"
    outside.write_bytes(b"\x89PNG\r\n\x1a\n")
    found = _attach(f"look at @{outside}", tmp_path)
    assert not found.images
    assert any("outside the working directory" in p for p in found.problems)
