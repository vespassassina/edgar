"""Units and the pairing invariant [CTX-4, ADR-0016].

The invariant is the one every provider enforces with a 400: an assistant message
with tool calls is immediately followed by exactly one tool message whose result
ids equal the call ids, one to one. A *unit* is the smallest slice of transcript
that can be removed, stubbed or summarised without breaking it: a call message
together with its result message, or any other single message. Compaction,
cancellation and /steer all work on unit boundaries, so the invariant holds by
construction rather than by repair.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from edgar.core.message import Message


class PairingViolation(Exception):
    """A transcript no provider would accept. Always a harness bug."""


@dataclass(frozen=True, slots=True)
class Unit:
    messages: tuple[Message, ...]

    @property
    def is_tool_exchange(self) -> bool:
        return len(self.messages) == 2


def units(transcript: Sequence[Message]) -> list[Unit]:
    out: list[Unit] = []
    i = 0
    while i < len(transcript):
        message = transcript[i]
        following = transcript[i + 1] if i + 1 < len(transcript) else None
        if message.tool_calls and following is not None and following.role == "tool":
            out.append(Unit((message, following)))
            i += 2
        else:
            out.append(Unit((message,)))
            i += 1
    return out


def pairing_violations(transcript: Sequence[Message]) -> list[str]:
    problems: list[str] = []
    for i, message in enumerate(transcript):
        calls = [c.id for c in message.tool_calls]
        results = [r.tool_use_id for r in message.tool_results]
        where = f"message {i} ({message.role})"
        if calls and message.role != "assistant":
            problems.append(f"{where}: tool calls outside an assistant message")
        if results and message.role != "tool":
            problems.append(f"{where}: tool results outside a tool message")
        if calls and len(set(calls)) != len(calls):
            problems.append(f"{where}: duplicate tool call ids")
        if calls and (i + 1 == len(transcript) or transcript[i + 1].role != "tool"):
            problems.append(f"{where}: tool calls not followed by a tool message")
        if message.role == "tool":
            previous = transcript[i - 1] if i else None
            if previous is None or not previous.tool_calls:
                problems.append(f"{where}: tool message without calls before it")
            elif sorted(results) != sorted(c.id for c in previous.tool_calls):
                problems.append(f"{where}: results do not match the calls one to one")
    return problems


def assert_pairing(transcript: Sequence[Message]) -> None:
    problems = pairing_violations(transcript)
    if problems:
        raise PairingViolation("; ".join(problems))


def complete_prefix(transcript: Sequence[Message]) -> list[Message]:
    """The transcript cut back to the last complete unit.

    Used wherever a request is built while a unit may still be open: a trailing
    assistant message whose calls have no results yet is dropped (/btw, CLI-24).
    """
    out = list(transcript)
    if out and out[-1].tool_calls:
        out.pop()
    return out
