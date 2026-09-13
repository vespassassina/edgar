"""Deterministic tool-call repair [PRV-16].

Small local models often get the call right and the syntax wrong: JSON in a code
fence, a sentence after the object, or a call written as text because the server
has no native tool format. A fixed list of syntactic repairs, each pure, tried in
order. Nothing semantic: no guessed argument values, no fuzzy tool names. What
this cannot repair goes back to the model as a validation error, which is the
retry signal models are trained on.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from typing import Any

_FENCED = re.compile(r"^```[\w-]*[ \t]*\n?(.*?)\n?```$", re.S)
_FENCES = re.compile(r"```[\w-]*[ \t]*\n?(.*?)\n?```", re.S)
_ARG_KEYS = ("arguments", "parameters", "input")


def arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Native tool-call arguments → (the object, the repair used), or (None, None)."""
    if not raw.strip():
        return {}, None
    value = _object(raw)
    if value is not None:
        return value, None
    inner = _unfence(raw)
    if inner is not None and (value := _object(inner)) is not None:
        return value, "fence"
    value = _leading_object(raw if inner is None else inner)
    return (value, "trailing-text") if value is not None else (None, None)


def text_call(
    text: str, tools: Collection[str], *, anywhere: bool
) -> tuple[str, dict[str, Any], str] | None:
    """A reply whose text is a tool call → (tool, arguments, repair), else None.

    By default the whole reply must be the call, fenced or not, so a model that is
    explaining some JSON is never taken to be calling a tool. `anywhere` is for
    servers without native tools, where text is the only way to call one.
    """
    stripped = text.strip()
    inner = _unfence(stripped)
    candidates = [(inner, "fence")] if inner is not None else [(stripped, "text-call")]
    if anywhere:
        candidates += [(m[1], "fence") for m in _FENCES.finditer(text)]
        if "{" in text:
            candidates.append((text[text.index("{") :], "text-call"))
    for candidate, repair in candidates:
        value = _leading_object(candidate)
        call = _as_call(value, tools) if value is not None else None
        if call is not None:
            return call[0], call[1], repair
    return None


def _as_call(value: dict[str, Any], tools: Collection[str]) -> tuple[str, dict[str, Any]] | None:
    name = value.get("name")
    if not isinstance(name, str) or name not in tools:
        return None
    args: Any = next((value[k] for k in _ARG_KEYS if k in value), {})
    if isinstance(args, str):  # arguments encoded twice, as OpenAI's own format does
        args = _object(args)
    return (name, args) if isinstance(args, dict) else None


def _unfence(text: str) -> str | None:
    match = _FENCED.match(text.strip())
    return match[1] if match else None


def _object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _leading_object(text: str) -> dict[str, Any] | None:
    """The JSON object `text` starts with, ignoring whatever follows it."""
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
