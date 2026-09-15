"""The caller side of `decide()`: everything that needs I/O [PERM-6, PERM-7, PERM-10].

It resolves the subject, builds the `Policy` from config, grants and the session's
state, asks the user when the answer is Ask, remembers "session" and "always"
answers, and emits one `PermissionResolved` per decision. `decide()` stays pure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from edgar.core.events import EventBus, PermissionResolved
from edgar.permissions.matcher import Subject
from edgar.permissions.matcher import subject as resolve
from edgar.permissions.policy import Allow, Ask, Decision, Deny, Policy, decide
from edgar.storage.db import Store
from edgar.tools.base import ToolSchema

Answer = Literal["once", "session", "always", "deny"]
Asker = Callable[[str, str, str], Awaitable[Answer]]  # tool, subject, reason


@dataclass
class Guard:
    base: Policy  # rules and paths from config; mode, cwd and taint come per call
    asker: Asker | None = None  # None: non-interactive, every Ask is a denial
    store: Store | None = None  # where "always" goes
    granted: set[tuple[str, str]] = field(default_factory=set)
    prompt_denials: int = 0  # Asks nobody could answer: `-p` exits 5 [PERM-7]
    # A subagent shares its parent's Guard (BLUEPRINT §9), so concurrent `task`
    # calls that fan out [TOOL-12] can each reach `_ask()` at once; the lock
    # makes the asker see one prompt at a time, never several interleaved.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        if self.store is not None:
            self.granted |= {(tool, s) for _, tool, s, _ in self.store.grants()}

    async def check(
        self,
        tool: ToolSchema,
        args: dict[str, Any],
        *,
        cwd: Path,
        mode: str,
        tainted: bool,
        call_id: str,
        bus: EventBus,
        subject: Subject | None = None,
        agent_id: str = "main",
    ) -> Allow | Deny:
        s = subject or resolve(args, cwd)
        policy = replace(
            self.base,
            cwd=cwd.resolve(),
            mode=mode,
            tainted=tainted,
            interactive=self.asker is not None,
            grants=frozenset(self.granted),
        )
        decision: Decision = decide(tool, s, policy)
        if isinstance(decision, Ask):
            decision = await self._ask(tool.name, s.text, decision, agent_id)
        if isinstance(decision, Deny) and decision.needed_prompt:
            self.prompt_denials += 1
        reason = decision.reason if isinstance(decision, Deny) else ""
        verdict = "allow" if isinstance(decision, Allow) else "deny"
        bus.emit(
            PermissionResolved(
                id=call_id,
                decision=verdict,
                source=decision.source,
                tool=tool.name,
                subject=s.text,
                reason=reason,
            )
        )
        return decision

    async def _ask(self, tool: str, text: str, ask: Ask, agent_id: str) -> Allow | Deny:
        assert self.asker is not None  # decide() turns Ask into Deny when non-interactive
        reason = ask.reason if agent_id == "main" else f"[{agent_id}] {ask.reason}"
        async with self._lock:  # one prompt at a time, however many agents are asking
            answer = await self.asker(tool, text, reason)
        if answer == "deny":
            return Deny("you said no", "user")
        if answer in ("session", "always"):
            self.granted.add((tool, text))
        if answer == "always" and self.store is not None and ask.source != "control":
            self.store.grant(tool, text)  # a grant, never a config edit [PERM-6]
        return Allow("user")
