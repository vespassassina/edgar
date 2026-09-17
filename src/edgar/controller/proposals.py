"""The eight things the controller may ask for, and nothing else [CTRL-4, CTRL-5]."""

# The controller answers with one JSON object. This file turns that object into one
# of eight frozen types, or into a Rejected saying why it could not. There is no
# ninth path: a name that is not in ACTIONS never reaches a builder, so a model that
# invents an action gets a logged rejection rather than a surprise [CTRL-5].
#
#   compact              compact earlier from now on
#   switch_model         run on another model the project already names [ROUTE-8]
#   tighten_policy       narrow permissions; never widen them [CTRL-8]
#   warn_user            say something; block nothing
#   abort                stop acting: this session goes read-only
#   propose_instruction  a diff for a human to apply by hand [CTRL-12]
#   propose_skill        a diff for a skill file [CTRL-13]
#   noop                 the trip was a false alarm
#
# There is deliberately no `learn` action. The controller reads an outline built from
# a session it cannot vouch for, so letting it write a fact would be the fifth hole
# ADR-0017 closed. `warn_user` can suggest `/remember`; a human types it.
#
# The shape mirrors permissions/policy.py's Allow | Deny | Ask: a tagged union of
# small frozen dataclasses, matched with isinstance by whoever acts on it.

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from edgar.config.schema import ModelSection
from edgar.controller.tighten import Malformed, Narrowing
from edgar.providers.routing import Route

ACTIONS = (
    "compact",
    "switch_model",
    "tighten_policy",
    "warn_user",
    "abort",
    "propose_instruction",
    "propose_skill",
    "noop",
)


@dataclass(frozen=True, slots=True)
class Compact:
    compact_at: float  # the new [context] compact_at; only ever lower than now
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SwitchModel:
    model: str  # checked against targets() before this exists [ROUTE-8]
    reason: str = ""


@dataclass(frozen=True, slots=True)
class TightenPolicy:
    want: Narrowing
    reason: str = ""


@dataclass(frozen=True, slots=True)
class WarnUser:
    message: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Abort:
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ProposeInstruction:
    title: str
    body: str  # the lines a human might add to AGENTS.md; edgar never writes them
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ProposeSkill:
    name: str  # a skill folder name, used as a file name: kept to [a-z0-9-]
    body: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Noop:
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Rejected:
    """A malformed or out-of-bounds proposal. It is logged and discarded; it is never
    raised, because nothing the controller does may fail the turn [CTRL-5, CTRL-11]."""

    problem: str
    raw: str = ""


Proposal = (
    Compact
    | SwitchModel
    | TightenPolicy
    | WarnUser
    | Abort
    | ProposeInstruction
    | ProposeSkill
    | Noop
)

MAX_TEXT = 2000  # a proposal is a sentence and a short body, never a document


def targets(models: ModelSection, rules: tuple[Route, ...]) -> frozenset[str]:
    """Where `switch_model` may point [ROUTE-8].

    The escalation chain the requirement also allows is M15's and does not exist
    yet, so today the target set is exactly the models this project already names:
    every `[[route]]` rule's model, plus each role's own `[model]` binding. A string
    outside it is rejected, which is what keeps the controller from routing your
    prompts to a host you never configured [PRV-15].
    """
    named = (models.default, models.compactor, models.controller, models.condenser)
    return frozenset({rule.model for rule in rules} | {name for name in named if name})


def parse(raw: str, *, models: frozenset[str]) -> Proposal | Rejected:
    """One JSON object from the controller into one typed proposal [CTRL-5]."""
    # 1. It has to be JSON, and an object. Small models fence their answers, so the
    #    fence comes off first; everything else is the model's problem to get right.
    try:
        data = json.loads(_unfence(raw))
    except ValueError as exc:
        return Rejected(f"not JSON: {exc}", raw)
    if not isinstance(data, dict):
        return Rejected("not a JSON object", raw)
    # 2. The action has to be one of the eight. This is the whitelist [CTRL-4].
    action = data.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        return Rejected(f"{action!r} is not one of the eight actions", raw)
    # 3. Its own builder checks its own fields, and says so when they are wrong.
    try:
        return BUILDERS[action](data, _text(data.get("reason"), "reason"), models)
    except Malformed as exc:
        return Rejected(f"{action}: {exc}", raw)


def _unfence(raw: str) -> str:
    # ```json { … } ``` is the most common way an answer arrives wrapped.
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[-1]
    return body.rsplit("```", 1)[0]


def _text(value: object, name: str, *, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise Malformed(f"{name} must be a non-empty string")
    return value.strip()[:MAX_TEXT]


def _compact(data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    value = data.get("compact_at")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise Malformed("compact_at must be a number")
    if not 0.10 <= float(value) <= 0.95:
        raise Malformed("compact_at must be between 0.10 and 0.95")
    return Compact(float(value), reason)


def _switch_model(data: dict[str, object], reason: str, models: frozenset[str]) -> Proposal:
    model = _text(data.get("model"), "model", required=True)
    # ROUTE-8, enforced here rather than at apply time: an arbitrary model string
    # never becomes a proposal at all, so there is one place to read the rule.
    if model not in models:
        named = ", ".join(sorted(models)) or "none"
        raise Malformed(f"{model!r} is not a configured routing target (have: {named})")
    return SwitchModel(model, reason)


def _tighten_policy(data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    want = Narrowing.from_dict(data)
    if want.is_empty():
        raise Malformed("nothing to tighten")
    return TightenPolicy(want, reason)


def _warn_user(data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    return WarnUser(_text(data.get("message"), "message", required=True), reason)


def _abort(_data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    return Abort(reason)


def _propose_instruction(data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    title = _text(data.get("title"), "title", required=True)
    return ProposeInstruction(title, _text(data.get("body"), "body", required=True), reason)


def _propose_skill(data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    name = _text(data.get("name"), "name", required=True).lower()
    # The name becomes a file name under .edgar/proposals/, so it is not allowed to
    # be a path. Anything but a plain slug is refused rather than sanitised: a
    # sanitised name is a name nobody asked for [SKL-11].
    if not name.replace("-", "").isalnum() or len(name) > 60:
        raise Malformed(f"{name!r} is not a skill name ([a-z0-9-], up to 60)")
    return ProposeSkill(name, _text(data.get("body"), "body", required=True), reason)


def _noop(_data: dict[str, object], reason: str, _: frozenset[str]) -> Proposal:
    return Noop(reason)


Builder = Callable[[dict[str, object], str, frozenset[str]], Proposal]

BUILDERS: Mapping[str, Builder] = {
    "compact": _compact,
    "switch_model": _switch_model,
    "tighten_policy": _tighten_policy,
    "warn_user": _warn_user,
    "abort": _abort,
    "propose_instruction": _propose_instruction,
    "propose_skill": _propose_skill,
    "noop": _noop,
}


@dataclass(frozen=True, slots=True)
class Outline:
    """Everything the controller is told about the turn [CTRL-4, SKL-9, MEM-9].

    It is counts and names: which checks tripped, which tools ran, how many calls
    failed, what the declared check said. No tool output, no error text, no fetched
    content, no prompt body — the same discipline the learner works under, for the
    same reason: the controller's answer changes how edgar behaves, so what it reads
    has to be text edgar wrote about itself.
    """

    tripped: str
    tools: tuple[str, ...] = ()
    failures: int = 0
    verification: str = "unverified"
    reason: str = "stop"
    models: tuple[str, ...] = field(default_factory=tuple)
    mode: str = "ask"

    def render(self) -> str:
        tools = ", ".join(self.tools) or "none"
        return "\n".join(
            [
                f"what tripped: {self.tripped}",
                f"tools called: {tools}",
                f"calls that failed: {self.failures}",
                f"declared check: {self.verification}",
                f"the turn ended: {self.reason}",
                f"permission mode: {self.mode}",
                f"models you may switch to: {', '.join(sorted(self.models)) or 'none'}",
            ]
        )
