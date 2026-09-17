"""Staged compaction, cheapest first, on whole units [CTX-3, CTX-5, CTX-11, ADR-0016].

Once the prompt passes `compact_at` of the usable window, stages run until it is
under `compact_to`:

- **S1 elide**: in turns older than `keep_last_turns`, each tool result becomes a
  one-line stub and thinking is dropped. No model call; the blocks stay.
- **S2 summarise**: those turns fold into one summary message of fixed shape,
  with any earlier summary folded in. One model call.
- **S3 overflow**: only if the prompt still does not fit the window, elide inside
  the recent turns too, all but the last unit; then `ContextOverflow`.

Every stage is a pure function of the view and a cut point on a turn boundary,
so the pairing invariant holds by construction, and `apply()` replays a recorded
compaction exactly on `--resume` [CTX-14]. The first prompt is never compacted.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from edgar.context.prompts import load_prompt
from edgar.context.tokens import approx_tokens, message_text
from edgar.context.working import render
from edgar.core.errors import ContextOverflow
from edgar.core.events import Compacted, EventBus
from edgar.core.message import Message, TextBlock, ThinkingBlock, ToolResultBlock
from edgar.core.units import units
from edgar.providers.base import plus

if TYPE_CHECKING:
    from edgar.core.loop import Runtime
from edgar.core.session import Session

ELIDED = "[elided: "


def turn_starts(view: list[Message]) -> list[int]:
    """Where each turn begins: a prompt the user typed, not a steer or a summary."""
    return [i for i, m in enumerate(view) if m.role == "user" and not m.meta.get("via")]


def elide(view: list[Message], upto: int) -> list[Message]:
    """S1: before `upto`, tool results become stubs and thinking goes, except in the
    turn in progress, whose thinking providers need unchanged [CTX-4, CTX-11]."""
    calls = {c.id: c for m in view[:upto] for c in m.tool_calls}
    current = (turn_starts(view) or [0])[-1]
    out = []
    for i, m in enumerate(view[:upto]):
        drop = ThinkingBlock if i < current else ()
        kept = tuple(_stub(b, calls) for b in m.content if not isinstance(b, drop))
        out.append(replace(m, content=kept) if kept else m)
    return out + view[upto:]


def _stub(block: Any, calls: dict[str, Any]) -> Any:
    if not isinstance(block, ToolResultBlock) or block.text.startswith(ELIDED):
        return block
    call = calls.get(block.tool_use_id)
    what = f"{call.name} {json.dumps(call.args, ensure_ascii=False)[:60]}" if call else "result"
    where = f" · full output {block.blob}" if block.blob else ""
    stub = f"{ELIDED}{what} · ~{approx_tokens(block.text):,} tokens{where}]"
    return replace(block, content=(TextBlock(stub),)) if len(stub) < len(block.text) else block


def fold(view: list[Message], upto: int, summary: str) -> list[Message]:
    """S2: everything between the first prompt and `upto` becomes one summary,
    an earlier summary included, so there is at most one [CTX-5, CTX-6]."""
    return [view[0], Message.user(summary, via="summary"), *view[upto:]]


def rewind(view: list[Message], turns: int) -> tuple[list[Message], list[str]]:
    """`/undo N`: the last N turns go, whole. Returns the files `write` and `edit`
    changed in them, which stay changed on disk [CLI-26, OQ-10]."""
    starts = turn_starts(view)
    cut = starts[-turns] if turns <= len(starts) else 0
    files = [
        str(c.args.get("path"))
        for m in view[cut:]
        for c in m.tool_calls
        if c.name in ("write", "edit")
    ]
    return view[:cut], sorted(set(files))


def apply(view: list[Message], entry: dict[str, Any]) -> list[Message]:
    """Replay one recorded change to the view: a compaction stage, reset or undo."""
    kind = entry["type"]
    if kind == "compaction":
        if entry["stage"] == "S2":
            return fold(view, entry["upto"], entry["summary"])
        return elide(view, entry["upto"])
    if kind == "reset":
        return []
    if kind == "undo":
        return rewind(view, entry["turns"])[0]
    return view


async def compact(
    session: Session, rt: Runtime, *, force: bool = False, focus: str | None = None
) -> None:
    """Run the stages the prompt needs. `force` (`/compact`) summarises the old
    turns even under the threshold; below it, autocompact is a no-op [CTX-7, CTX-8]."""
    cfg, caps = rt.context, rt.provider.capabilities
    # The window less the output reserve, which never takes more than half of it.
    usable = caps.max_context - min(caps.max_output, caps.max_context // 2)
    system = Message("system", (TextBlock(rt.system_prompt),))

    # Working state is not in the transcript, so compaction cannot touch it, but it
    # is in the request: count it or every stage under-reads the prompt [CTX-18].
    block = render(session.working)
    fixed = [system, *([block] if block else [])]

    def size(view: list[Message]) -> int:
        return rt.provider.count_tokens([*fixed, *view])

    view = session.transcript
    before = size(view)
    if not force and (not cfg.autocompact or before <= cfg.compact_at * usable):
        return
    target = cfg.compact_to * usable
    starts = turn_starts(view)
    keep = min(max(cfg.keep_last_turns, 1), len(starts))
    cut = starts[-keep] if starts else 0  # the turn in progress stays
    stages: list[dict[str, Any]] = []

    def stage(name: str, new: list[Message], upto: int, summary: str | None = None) -> None:
        nonlocal view
        if new != view:
            view = new
            stages.append({"type": "compaction", "stage": name, "upto": upto, "summary": summary})

    stage("S1", elide(view, cut), cut)
    cost: float | None = 0.0
    fresh = any(m.meta.get("via") != "summary" for m in view[1:cut])  # not just the summary
    if fresh and (force or size(view) > target):
        summary, cost = await _summarise(view[1:cut], rt, session, focus)
        stage("S2", fold(view, cut, summary), cut, summary)
    if size(view) > usable and view:
        last = len(view) - len(units(view)[-1].messages)
        stage("S3", elide(view, last), last)
    if size(view) > usable:
        raise ContextOverflow(
            f"the prompt needs ~{size(view):,} tokens; {rt.name} has room for {usable:,}",
            hint="try /compact, a lower context.keep_last_turns, or a model with a larger window",
        )
    session.transcript, session.cost = view, plus(session.cost, cost)
    for entry in stages:
        session.record(entry)
    if stages:  # else nothing could go: the prompt fits, above target but under the window
        names = "+".join(s["stage"] for s in stages)
        rt.bus.emit(Compacted(stages=names, before=before, after=size(view), cost=cost))


async def _summarise(
    old: list[Message], rt: Runtime, session: Session, focus: str | None
) -> tuple[str, float | None]:
    """One call to the compactor, the main model unless `model.compactor` names
    another [PRV-15]. It sees the elided turns, never the full tool output."""
    provider, model = rt.compactor or (rt.provider, rt.model)
    lines = "\n\n".join(f"{m.role}: {message_text(m)}" for m in old)
    ask = f"Focus on: {focus}\n\n{lines}" if focus else lines
    instructions = Message("system", (TextBlock(load_prompt(session.cwd, "summarise").text),))
    response = await provider.stream(
        [instructions, Message.user(ask)], [], model=model, bus=EventBus(), reasoning=False
    )
    text = f"Summary of the earlier conversation, by edgar's compactor:\n\n{response.message.text}"
    return text, response.cost
