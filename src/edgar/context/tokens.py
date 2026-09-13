"""Token counting. Approximate for now; exact counts come from providers (OQ-3, M2)."""

from __future__ import annotations

import json
from collections.abc import Sequence

from edgar.core.message import Message, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock

CHARS_PER_TOKEN = 4


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


def approx_message_tokens(messages: Sequence[Message]) -> int:
    return sum(approx_tokens(message_text(m)) for m in messages)
