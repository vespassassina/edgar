"""Stage S0 of the context pipeline: large output keeps its head and tail [TOOL-4, CTX-13].

The full text goes to a blob the model can `read` with an offset, so nothing is
lost, only kept out of the prompt. Image bytes take the same road and never come
back: the block keeps only the reference [ADR-0052].
"""

# Two spills, one blob directory:
#
#   spill(text)        1. under the limit: nothing happens
#                      2. over it: write the whole text to a blob
#                      3. keep the head and the tail, with a marker between them
#
#   spill_image(bytes) 1. read the media type and the dimensions off the header
#                      2. not an image edgar knows: say so, spill nothing
#                      3. write the bytes to a blob, hand back an ImageBlock
#
# Both name their blob through `_blob()`, so one rule sanitises every file name
# and one line creates the directory.

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from edgar.context.tokens import CHARS_PER_TOKEN
from edgar.core.message import ImageBlock

# The four formats every vision model takes, by the bytes that start the file.
SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # only when bytes 8..12 are WEBP; checked below
)
SUFFIXES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


@dataclass(frozen=True, slots=True)
class Spilled:
    text: str
    truncated: bool
    blob: Path | None


def _blob(blob_dir: Path, name: str, suffix: str) -> Path:
    """One blob path rule for text and images: a safe name under the session's dir."""
    blob = blob_dir / (re.sub(r"[^A-Za-z0-9_-]", "_", name) + suffix)
    blob.parent.mkdir(parents=True, exist_ok=True)
    return blob


def spill(text: str, *, max_tokens: int, blob_dir: Path, name: str, root: Path) -> Spilled:
    """`root` is the working directory; the marker names the blob relative to it."""
    limit = max_tokens * CHARS_PER_TOKEN
    if len(text) <= limit:
        return Spilled(text, False, None)
    blob = _blob(blob_dir, name, ".txt")
    blob.write_text(text, encoding="utf-8", newline="")
    shown = blob.relative_to(root) if blob.is_relative_to(root) else blob
    head, tail = text[: limit // 2], text[-(limit // 2) :]
    omitted = len(text) - len(head) - len(tail)
    marker = (
        f"\n[… {omitted:,} characters omitted. Full output: {shown.as_posix()}"
        " — use read with offset to see the rest …]\n"
    )
    return Spilled(head + marker + tail, True, blob)


def spill_image(data: bytes, *, blob_dir: Path, name: str) -> ImageBlock | None:
    """The bytes go to a blob and the block keeps the reference; None when `data`
    is not one of the four image formats edgar knows [ADR-0052]."""
    kind = media_type(data)
    if kind is None:
        return None
    blob = _blob(blob_dir, name, SUFFIXES[kind])
    blob.write_bytes(data)
    width, height = geometry(kind, data)
    return ImageBlock(kind, blob.as_posix(), width, height)


def media_type(data: bytes) -> str | None:
    """PNG, JPEG, GIF or WebP, read off the first bytes; None for anything else."""
    for signature, kind in SIGNATURES:
        if data.startswith(signature) and (kind != "image/webp" or data[8:12] == b"WEBP"):
            return kind
    return None


def geometry(kind: str, data: bytes) -> tuple[int, int]:
    """Width and height in pixels, or (0, 0) when the header does not give them —
    counting then falls back to a flat estimate rather than guessing [ADR-0052]."""
    try:
        if kind == "image/png":
            return _int(data[16:20]), _int(data[20:24])
        if kind == "image/gif":
            return _int(data[6:8], "little"), _int(data[8:10], "little")
        if kind == "image/jpeg":
            return _jpeg(data)
        return _webp(data)
    except (IndexError, ValueError):  # truncated or malformed: unknown, never a crash
        return 0, 0


def _int(raw: bytes, order: str = "big") -> int:
    return int.from_bytes(raw, "little" if order == "little" else "big")


def _jpeg(data: bytes) -> tuple[int, int]:
    # Walk the marker segments until a start-of-frame block says how big it is.
    # SOF markers are C0..CF except C4 (Huffman), C8 (extension) and CC (arithmetic).
    i = 2
    while i + 9 < len(data) and data[i] == 0xFF:
        marker, length = data[i + 1], _int(data[i + 2 : i + 4])
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return _int(data[i + 7 : i + 9]), _int(data[i + 5 : i + 7])
        i += 2 + length
    return 0, 0


def _webp(data: bytes) -> tuple[int, int]:
    # Three containers, each keeping the size somewhere else in its first chunk.
    chunk = data[12:16]
    if chunk == b"VP8X":  # extended: 24-bit width and height, both minus one
        return _int(data[24:27], "little") + 1, _int(data[27:30], "little") + 1
    if chunk == b"VP8 ":  # lossy: 14 bits each, after the frame tag and sync code
        return _int(data[26:28], "little") & 0x3FFF, _int(data[28:30], "little") & 0x3FFF
    if chunk == b"VP8L":  # lossless: 14 bits each, packed, both minus one
        bits = _int(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return 0, 0
