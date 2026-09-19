"""Five numbers, sometimes one call, never a failed turn [CTRL-1, CTRL-3, CTRL-9, CTRL-11]."""

# What happens after every turn, in order:
#
#   1. TurnStarted     start the clock; a new turn has failed nothing yet
#   2. ToolFinished    count the failures, which is what an error streak is made of
#   3. VerifyFinished  remember whether the declared check passed
#   4. TurnFinished    build Signals, ask triggers.tripped()
#   5. nothing tripped end here: no call, no cost, no latency. The common case
#   6. something did   fire one model call as a background task, and return at once
#   7. the answer      parse it, apply it, announce it on the bus
#
# Step 6 is the only interesting line here. The bus is synchronous and a model call
# is not, so the gate does what extensions/hooks.py already does with a fired hook:
# asyncio.ensure_future, plus a module-level set holding the task so asyncio cannot
# collect it mid-flight. The turn is over either way. A `-p` run that exits
# immediately may drop a call still in flight, which is CTRL-11 working as written:
# whatever the controller was about to say, the turn does not wait for it.
#
# The call passes NO TOOLS AT ALL. ADR-0008 asked for a "hard-limited tool set"; the
# only limit that needs no maintenance is zero. Everything the controller may do is
# in its answer, and its answer is one of eight shapes [CTRL-4].
#
# Nothing in here raises into a session. _look() is wrapped once, at the top, and a
# failure is written to the rejected table instead: a housekeeping mechanism that can
# break your session is worse than no housekeeping at all [CTRL-11].

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edgar.config.schema import Config
from edgar.controller.apply import Site, apply
from edgar.controller.proposals import (
    Outline,
    Proposal,
    ProposeSkill,
    Rejected,
    parse,
    targets,
)
from edgar.controller.store import Controls
from edgar.controller.triggers import Signals, summary, tripped
from edgar.core.events import (
    ControllerActed,
    Event,
    EventBus,
    PromptSteered,
    PromptTyped,
    SkillsActivated,
    ToolFinished,
    TurnFinished,
    TurnStarted,
    VerifyFinished,
)
from edgar.core.message import ErrorRecord, Message
from edgar.permissions.guard import Guard
from edgar.providers.registry import resolve
from edgar.providers.routing import RoutingContext, routes_from_config, select_model
from edgar.skills.discovery import discover
from edgar.storage.db import Store

# Held for the same reason extensions/hooks.py holds its tasks: asyncio keeps only a
# weak reference, so a task nobody holds can be collected before it finishes.
_running: set[asyncio.Task[None]] = set()

# Everything the controller is told about its job. It is a prompt, not a policy: the
# policy is proposals.py and tighten.py, which refuse whatever this text failed to
# prevent. Nothing here is load-bearing; every rule in it is enforced in code too.
BRIEF = """You watch one agent session. Answer with one JSON object and nothing else:

{"action": NAME, "reason": "one short sentence", ...fields}

The actions, and the fields each one takes:
  noop                 nothing worth changing
  warn_user            "message": what to tell the person
  compact              "compact_at": 0.10-0.95, start compacting earlier than now
  switch_model         "model": one of the models listed below, spelled exactly
  tighten_policy       "mode", "shell_deny", "write_paths" or "rules": stricter only
  abort                stop acting: the session goes read-only
  propose_instruction  "title", "body": a note for the person to apply by hand
  propose_skill        "name" (lowercase and dashes), "body": a procedure worth keeping

Prefer noop. You are being asked because a threshold was crossed, not because
anything is known to be wrong. You may not loosen a permission, you may not pick a
model that is not listed, and you may not save anything to memory."""


@dataclass
class Gate:
    """One session's controller, subscribed to one bus.

    Mutable for the reason `_Turn` in core/loop.py is: the counters are state shared
    between four events, and four setters would not make them less shared.
    """

    config: Config
    root: Path
    home: Path
    guard: Guard
    store: Controls
    bus: EventBus
    session: str = ""  # the session id, written into a learned skill's provenance
    window: int = 0  # the main model's context window, for token_fraction
    streak: int = 0  # turns in a row that ended with a failing tool call
    failed: int = 0  # failing tool calls in the turn running now
    started: float = 0.0
    checked: str = "unverified"
    tools: list[str] = field(default_factory=list)
    # The three below are read by the synthesis step only, and each is on ADR-0017's
    # safe list: a line a human typed, a line a human typed while it ran, the four
    # fields the harness computed about a failure, the names of skills it loaded.
    prompt: str = ""
    corrections: list[str] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    def __call__(self, event: Event) -> None:
        # A subagent's turn is not the unit a person thinks in, so the gate watches
        # the main loop only — the same line the learner's Recorder draws [SUB-3].
        if event.depth:
            return
        if isinstance(event, PromptTyped):
            self.prompt, self.corrections = event.text, []
        elif isinstance(event, PromptSteered):
            self.corrections.append(event.text)
        elif isinstance(event, SkillsActivated):
            self.skills = list(event.names)
        elif isinstance(event, TurnStarted):
            self.failed, self.started, self.checked, self.tools = 0, time.monotonic(), "", []
            self.errors = []
        elif isinstance(event, ToolFinished):
            self.tools.append(event.tool)
            self.failed += 0 if event.ok else 1
            self.errors += [event.error] if event.error is not None else []
        elif isinstance(event, VerifyFinished):
            self.checked = "passed" if event.ok else "failed"
        elif isinstance(event, TurnFinished):
            self._ended(event)
            self._synthesis()

    def _ended(self, event: TurnFinished) -> None:
        # 1. The streak is counted here, in this session, off the bus. It is
        #    deliberately not read out of learning/experience.py: the controller has
        #    to work with the whole learning package deleted [NFR-12].
        self.streak = self.streak + 1 if self.failed else 0
        signals = self._signals(event)
        names = tripped(signals, self.config.controller)
        if not names:
            return
        # 2. One call, in the background, and this returns immediately. Nothing
        #    below this line can reach the turn that just finished [CTRL-11].
        task = asyncio.ensure_future(self._look(signals, names, event.reason))
        _running.add(task)
        task.add_done_callback(_running.discard)

    def _signals(self, event: TurnFinished) -> Signals:
        # The five numbers, each from the cheapest honest source: the usage the
        # provider reported, the counters above, and the spend store `edgar cost`
        # reads. No cap configured means no burn rate, not a guessed one.
        cap = self.config.budget.daily_cost_cap
        spent = Store(self.home / ".edgar" / "edgar.db").spent() if cap else []
        return Signals(
            token_fraction=event.usage.input_tokens / self.window if self.window else 0.0,
            error_streak=self.streak,
            burn_rate=spent[0][1] / cap if cap and spent else 0.0,
            output_tokens=event.usage.output_tokens,
            wall_clock_s=time.monotonic() - self.started if self.started else 0.0,
        )

    def _outline(
        self, signals: Signals, names: tuple[str, ...], reason: str, at: frozenset[str]
    ) -> Outline:
        # Counts and names only: which checks tripped, which tools ran, how many
        # calls failed, what the declared check said. No tool output, no error text,
        # no prompt body — the discipline the learner works under [SKL-9, MEM-9].
        return Outline(
            tripped=summary(signals, names),
            tools=tuple(dict.fromkeys(self.tools)),
            failures=self.failed,
            verification=self.checked or "unverified",
            reason=reason,
            models=tuple(sorted(at)),
            mode=self.guard.base.mode,
        )

    async def _look(self, signals: Signals, names: tuple[str, ...], reason: str) -> None:
        # The one place an exception could escape into a session, so the one place
        # with a bare except. A refused or broken controller leaves a row in the
        # rejected table, which is what `edgar controller log` is for [CTRL-11].
        try:
            await self._ask(signals, names, reason)
        except Exception as exc:
            self.store.reject("", f"the controller did not answer: {exc}")

    async def _ask(self, signals: Signals, names: tuple[str, ...], reason: str) -> None:
        # 1. The controller's own model [CTRL-9]: a matching [[route]] rule, then the
        #    [model] controller binding, then the main model. Never one nobody named.
        rules = routes_from_config(self.config.later)
        ctx = RoutingContext(role="controller", mode=self.config.permissions.mode)
        provider, model = resolve(select_model(ctx, self.config.model, rules).model, self.config)
        # 2. One call, no tools, on a bus of its own so its deltas never land on the
        #    screen the finished turn just wrote to [CTRL-3].
        at = targets(self.config.model, rules)
        prompt = [
            Message.user(f"{BRIEF}\n\n---\n\n{self._outline(signals, names, reason, at).render()}")
        ]
        answer = await provider.stream(prompt, [], model=model, bus=EventBus(), reasoning=False)
        # 3. What comes back is text until parse() says otherwise [CTRL-5].
        proposal = parse(answer.message.text, models=at)
        if isinstance(proposal, Rejected):
            self.store.reject(proposal.raw, proposal.problem)
            self._announce("rejected", proposal.problem, 0)
            return
        self._act(proposal)

    # --- skill synthesis [SKL-8..12] -------------------------------------------
    #
    # A second, separate question asked of the same finished turn: was this worth
    # writing down? It hangs here rather than in learning/ because SKL-8 asks for
    # deterministic triggers in this gate, and this is where the turn is counted.
    #
    # learning/ is the other removable package, so it is imported inside the
    # function and a ModuleNotFoundError simply means no synthesis: either folder
    # can be deleted without the other noticing [NFR-12].

    def _synthesis(self) -> None:
        # 1. Off is off, and it is one comparison before anything is imported.
        if self.config.skills.synthesis == "off":
            return
        try:
            from edgar.learning.experience import Experience
            from edgar.learning.synthesis import Outline, Turn, triggers
        except ModuleNotFoundError:
            return
        # 1b. A skill this turn followed, on a turn that went badly, earns a line
        #     and eventually a patch. It runs first because it is arithmetic on
        #     what already happened, and because it can fire when nothing else
        #     does: a bad turn trips no synthesis trigger at all [SKL-14].
        self._observe()
        # 2. The turn, in the only terms SKL-9 allows. Tool names, not arguments.
        turn = Turn(
            prompt=self.prompt,
            corrections=tuple(self.corrections),
            tools=tuple(self.tools),
            errors=tuple(self.errors),
            verification=self.checked or "unverified",
            skills=tuple(self.skills),
        )
        # 3. Arithmetic decides whether a model is asked at all, exactly as above.
        names = triggers(turn, self.config.skills, Experience(self.root / ".edgar" / "learning.db"))
        if not names:
            return
        self._fire(self._synthesise(Outline.of(turn, names).render(), names))

    def _observe(self) -> None:
        # One line per skill the turn loaded, then one call once there are enough.
        # Nothing here reads tool output: observe() is handed names, ErrorRecords
        # and typed corrections, and there is no fourth argument [SKL-9, SKL-14].
        from edgar.learning.observations import notes, observe, outline

        for name in self.skills:
            seen = observe(
                self.root,
                name,
                errors=tuple(self.errors),
                corrections=tuple(self.corrections),
                verification=self.checked or "unverified",
            )
            skill = discover(self.root, self.home).skills.get(name)
            if seen < self.config.skills.distill_after or skill is None:
                continue
            body = skill.path.read_text(encoding="utf-8")
            asked = outline(name, body, notes(self.root, name))
            self._fire(self._synthesise(asked, ("distilled",), brief="patch"))

    def _fire(self, work: Coroutine[Any, Any, None]) -> None:
        # The same background-task dance as _ended(): the turn is over, and nothing
        # started here may reach it [CTRL-11].
        task = asyncio.ensure_future(work)
        _running.add(task)
        task.add_done_callback(_running.discard)

    async def _synthesise(
        self, outline: str, names: tuple[str, ...], *, brief: str = "write"
    ) -> None:
        # Wrapped like _look() and for the same reason: housekeeping never fails a
        # turn, and a synthesiser that breaks leaves a row in the rejected table.
        try:
            await self._ask_skill(outline, names, brief)
        except Exception as exc:
            self.store.reject("", f"the synthesiser did not answer: {exc}")

    async def _ask_skill(self, outline: str, names: tuple[str, ...], brief: str) -> None:
        from edgar.learning.observations import PATCH_BRIEF
        from edgar.learning.synthesis import BRIEF

        told = BRIEF if brief == "write" else PATCH_BRIEF

        # 1. The same model, the same no-tools call, the same parser. What differs
        #    is the brief and the outline, which is the whole of SKL-9.
        rules = routes_from_config(self.config.later)
        ctx = RoutingContext(role="controller", mode=self.config.permissions.mode)
        provider, model = resolve(select_model(ctx, self.config.model, rules).model, self.config)
        prompt = [Message.user(f"{told}\n\n---\n\n{outline}")]
        answer = await provider.stream(prompt, [], model=model, bus=EventBus(), reasoning=False)
        proposal = parse(answer.message.text, models=targets(self.config.model, rules))
        # 2. Only one of the eight means anything here. A synthesiser that answers
        #    `tighten_policy` is answering a question nobody asked it [CTRL-4].
        if isinstance(proposal, Rejected):
            self.store.reject(proposal.raw, proposal.problem)
            self._announce("rejected", proposal.problem, 0)
            return
        if not isinstance(proposal, ProposeSkill):
            self._announce("noop", "the synthesiser proposed no skill", 0)
            return
        self._act(proposal, trigger=",".join(names))

    def _act(self, proposal: Proposal, trigger: str = "") -> None:
        # 4. Apply it, and adopt a tightened policy if one came back. Guard is a
        #    mutable dataclass whose check() rebuilds from `base` on every call, so
        #    replacing `base` holds for the rest of this session and for nothing
        #    else: it is never written to config [PERM-8, ADR-0021].
        site = Site(
            self.store,
            self.root,
            self.guard.base,
            self.config.controller.dry_run,
            home=self.home,
            session=self.session,
            synthesis=self.config.skills.synthesis,
            verified=self.checked == "passed",
            trigger=trigger,
        )
        outcome = apply(proposal, site)
        if outcome.policy is not None:
            self.guard.base = outcome.policy
        self._announce(outcome.action, outcome.message, outcome.mutation_id)

    def _announce(self, action: str, message: str, mutation_id: int) -> None:
        # The only way the controller reaches a person: one event, rendered like any
        # other. It prints nothing itself [ADR-0011].
        self.bus.emit(ControllerActed(action=action, message=message, mutation_id=mutation_id))
