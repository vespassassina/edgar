"""Streamed responses in each provider's wire format, written from the providers'
documentation. They seed the synthetic cassettes and play the model in tests that
drive an adapter end to end. A recorded cassette replaces a synthetic one: that
is how a belief about an API gets checked against the API [ADR-0009 layer 3].
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Dialect = Literal["openai", "azure", "openrouter", "ollama", "compat"]


@dataclass
class Reply:
    text: str = ""
    reasoning: str = ""
    signature: str = "sig-abc"  # Anthropic signs thinking; replay must carry it back
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)  # id, name, args
    input_tokens: int = 21
    output_tokens: int = 7
    cost: float | None = None  # OpenRouter reports cost in the usage chunk
    pieces: int = 2  # how many deltas the text arrives in


def _sse(data: Any, event: str | None = None) -> str:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data)}\n\n"


def _pieces(text: str, n: int = 2) -> list[str]:
    size = max(1, -(-len(text) // n))
    return [text[i : i + size] for i in range(0, len(text), size)]


def openai_sse(reply: Reply, dialect: Dialect = "openai", model: str = "m") -> str:
    def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        choice = {"index": 0, "delta": delta, "finish_reason": finish}
        return _sse(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": [choice],
            }
        )

    out = []
    if dialect == "azure":  # content filtering results arrive first, with no choices
        out.append(_sse({"id": "", "choices": [], "prompt_filter_results": [{"prompt_index": 0}]}))
    out.append(chunk({"role": "assistant", "content": ""}))
    key = "reasoning_content" if dialect == "compat" else "reasoning"
    out += [chunk({key: piece}) for piece in _pieces(reply.reasoning)]
    out += [chunk({"content": piece}) for piece in _pieces(reply.text, reply.pieces)]
    for index, (call_id, name, args) in enumerate(reply.calls):
        text = json.dumps(args)
        if dialect == "ollama":  # Ollama sends each call whole, in one chunk
            function = {"name": name, "arguments": text}
            out.append(
                chunk({"tool_calls": [{"index": index, "id": call_id, "function": function}]})
            )
            continue
        first = {"index": index, "id": call_id, "type": "function"}
        out.append(chunk({"tool_calls": [first | {"function": {"name": name, "arguments": ""}}]}))
        out += [
            chunk({"tool_calls": [{"index": index, "function": {"arguments": piece}}]})
            for piece in _pieces(text, 3)
        ]
    out.append(chunk({}, "tool_calls" if reply.calls else "stop"))
    usage: dict[str, Any] = {
        "prompt_tokens": reply.input_tokens,
        "completion_tokens": reply.output_tokens,
        "total_tokens": reply.input_tokens + reply.output_tokens,
        "prompt_tokens_details": {"cached_tokens": 0},
    }
    if reply.cost is not None:
        usage["cost"] = reply.cost
    out.append(_sse({"id": "chatcmpl-1", "choices": [], "usage": usage}))
    out.append("data: [DONE]\n\n")
    return "".join(out)


def anthropic_sse(reply: Reply, model: str = "m") -> str:
    usage = {"input_tokens": reply.input_tokens, "output_tokens": 1}
    usage |= {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    message: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
    }
    message |= {"content": [], "stop_reason": None, "usage": usage}
    out = [_sse({"type": "message_start", "message": message}, "message_start")]
    out.append(_sse({"type": "ping"}, "ping"))
    index = 0

    def block(start: dict[str, Any], deltas: list[dict[str, Any]]) -> None:
        nonlocal index
        out.append(
            _sse(
                {"type": "content_block_start", "index": index, "content_block": start},
                "content_block_start",
            )
        )
        for delta in deltas:
            out.append(
                _sse(
                    {"type": "content_block_delta", "index": index, "delta": delta},
                    "content_block_delta",
                )
            )
        out.append(_sse({"type": "content_block_stop", "index": index}, "content_block_stop"))
        index += 1

    if reply.reasoning:
        deltas = [{"type": "thinking_delta", "thinking": p} for p in _pieces(reply.reasoning)]
        deltas.append({"type": "signature_delta", "signature": reply.signature})
        block({"type": "thinking", "thinking": "", "signature": ""}, deltas)
    if reply.text:
        block(
            {"type": "text", "text": ""},
            [{"type": "text_delta", "text": p} for p in _pieces(reply.text, reply.pieces)],
        )
    for call_id, name, args in reply.calls:
        block(
            {"type": "tool_use", "id": call_id, "name": name, "input": {}},
            [{"type": "input_json_delta", "partial_json": p} for p in _pieces(json.dumps(args), 3)],
        )
    stop = "tool_use" if reply.calls else "end_turn"
    delta = {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}}
    out.append(_sse(delta | {"usage": {"output_tokens": reply.output_tokens}}, "message_delta"))
    out.append(_sse({"type": "message_stop"}, "message_stop"))
    return "".join(out)


def ok(body: str) -> dict[str, Any]:
    return {"status": 200, "headers": {"content-type": "text/event-stream"}, "body": body}


def error(status: int, body: dict[str, Any], **headers: str) -> dict[str, Any]:
    head = {"content-type": "application/json"} | {
        k.replace("_", "-"): v for k, v in headers.items()
    }
    return {"status": status, "headers": head, "body": json.dumps(body)}
