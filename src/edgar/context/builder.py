"""Prompt assembly, most stable first [CTX-1].

M1 assembles the system prompt and the transcript. Instruction files, pinned facts,
the skill index, compaction and working state join in M5 and later, in the order
BLUEPRINT §8.1 fixes. Tool schemas travel beside the messages, in the request.
"""

from __future__ import annotations

from edgar.core.message import Message, TextBlock
from edgar.core.session import Session


def build(session: Session, system_prompt: str) -> list[Message]:
    return [Message("system", (TextBlock(system_prompt),)), *session.transcript]
