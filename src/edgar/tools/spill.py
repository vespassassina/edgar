"""Stage S0 of the context pipeline: large output keeps its head and tail [TOOL-4, CTX-13].

The full text goes to a blob the model can `read` with an offset, so nothing is
lost, only kept out of the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from edgar.context.tokens import CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class Spilled:
    text: str
    truncated: bool
    blob: Path | None


def spill(text: str, *, max_tokens: int, blob_dir: Path, name: str, root: Path) -> Spilled:
    """`root` is the working directory; the marker names the blob relative to it."""
    limit = max_tokens * CHARS_PER_TOKEN
    if len(text) <= limit:
        return Spilled(text, False, None)
    blob = blob_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', name)}.txt"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_text(text, encoding="utf-8", newline="")
    shown = blob.relative_to(root) if blob.is_relative_to(root) else blob
    head, tail = text[: limit // 2], text[-(limit // 2) :]
    omitted = len(text) - len(head) - len(tail)
    marker = (
        f"\n[… {omitted:,} characters omitted. Full output: {shown.as_posix()}"
        " — use read with offset to see the rest …]\n"
    )
    return Spilled(head + marker + tail, True, blob)
