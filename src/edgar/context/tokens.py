"""Token counting. Approximate for now; exact counts come from providers (OQ-3, M2)."""

from __future__ import annotations

import json
from collections.abc import Sequence

from edgar.core.message import (
    ImageBlock,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

CHARS_PER_TOKEN = 4

# A picture costs by its geometry, never by its bytes, and each family prices it
# its own way [ADR-0052]. Two rules cover every provider edgar speaks to:
#   1. anthropic: shrink to a 1568px longest side, then width * height / 750
#   2. everyone else (Chat Completions): shrink to fit 2048, then the short side
#      to 768, then 85 for the image plus 170 for each 512px tile it covers
TILE, BASE, PER_TILE = 512, 85, 170
PIXELS_PER_TOKEN = 750


def approx_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def message_text(message: Message) -> str:
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock | ThinkingBlock):
            parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            parts.append(block.name + json.dumps(block.args, ensure_ascii=False))
        elif isinstance(block, ToolResultBlock):
            parts.append(block.text)
    return "\n".join(parts)


def image_tokens(image: ImageBlock, family: str = "") -> int:
    # A header that could not be read left the size at 0: charge one tile's worth
    # rather than guess at a picture nobody measured.
    if not image.width or not image.height:
        return BASE + PER_TILE
    if family == "anthropic":
        width, height = _fit(image.width, image.height, 1568, 1568)
        return -(-width * height // PIXELS_PER_TOKEN)
    width, height = _fit(image.width, image.height, 2048, 768)
    return BASE + PER_TILE * (-(-width // TILE)) * (-(-height // TILE))


def _fit(width: int, height: int, longest: int, shortest: int) -> tuple[int, int]:
    # Shrink to fit the longest side, then the shortest side; never enlarge.
    scale = min(1.0, longest / max(width, height), shortest / min(width, height))
    return max(1, int(width * scale)), max(1, int(height * scale))


def approx_message_tokens(messages: Sequence[Message], family: str = "") -> int:
    text = sum(approx_tokens(message_text(m)) for m in messages)
    return text + sum(image_tokens(i, family) for m in messages for i in m.images)
