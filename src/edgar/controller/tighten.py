"""Policy may only tighten, never loosen [CTRL-8, PERM-8, ADR-0021]."""

# "Humans widen, machines tighten" is one of the constraints the whole project is
# arranged around, and this file is where the controller's half of it is decided.
# It is a pure function over two values, like permissions.decide(), so a generated
# test can throw thousands of policies and narrowings at it.
#
# The five fields a narrowing may touch, and what tightening means for each:
#
#   mode          only further along yolo -> auto -> ask -> read-only, never back
#   shell_deny    entries are added; an existing one is never dropped
#   write_paths   the list may only shrink, and only to patterns already in it
#   rules         a tool's verdict may go allow -> ask -> deny, never the other way,
#                 and a narrowing may never say "allow" at all
#   caveats       raw "KEY=VALUE" scope pairs [CAP-2], applied to the session's
#                 ticket (if one exists) through the same attenuate() `task`
#                 uses on delegation -- monotonic by construction, so unlike the
#                 four fields above this file never has to judge whether one is
#                 "tighter": broker/ticket.py already refuses to loosen anything
#
# Two rules are deliberately blunt. A narrowing may not introduce a *new*
# write_paths pattern even if it looks tighter, because "./src/**" being narrower
# than "./**" is a judgement about glob semantics that this function cannot make
# and a model should not be trusted to make. And an explicit `allow` is refused
# outright rather than compared, because an explicit allow overrides the mode's own
# default in permissions/policy.py, so it can widen even when it looks like a no-op.
#
# narrow() ends by checking its own answer with is_narrowing(). That looks
# redundant, and it is on purpose: the field-by-field rules above are where a
# mistake would live, and the final check is a second, simpler statement of the
# same property that a bug would have to defeat twice.

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from edgar.permissions.policy import Policy

MODES = ("yolo", "auto", "ask", "read-only")  # loosest first
VERDICTS = ("allow", "ask", "deny")  # loosest first


class Malformed(Exception):
    """A proposal edgar could not read. Raised here and in `proposals.py`, caught in
    `parse()`: it never travels further, because nothing the controller does may
    fail the turn [CTRL-5, CTRL-11]."""


@dataclass(frozen=True, slots=True)
class Narrowing:
    """What the controller asked to tighten. Every field is optional; an empty
    narrowing is refused by `proposals.py` before it gets here."""

    mode: str | None = None
    shell_deny: tuple[str, ...] = ()
    write_paths: tuple[str, ...] | None = None
    rules: Mapping[str, str] = field(default_factory=dict)  # tool -> ask | deny
    caveats: tuple[str, ...] = ()  # raw "KEY=VALUE" scope pairs [CAP-2]

    def is_empty(self) -> bool:
        return not (self.mode or self.shell_deny or self.write_paths or self.rules or self.caveats)

    def to_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "shell_deny": list(self.shell_deny),
                "write_paths": None if self.write_paths is None else list(self.write_paths),
                "rules": dict(self.rules),
                "caveats": list(self.caveats),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def from_json(raw: str) -> Narrowing:
        return Narrowing.from_dict(json.loads(raw))

    @staticmethod
    def from_dict(data: Mapping[str, object]) -> Narrowing:
        """Read the four fields out of a raw object, ignoring anything else in it.
        Types are checked here so `narrow()` never sees a surprise."""
        return Narrowing(
            mode=_mode(data.get("mode")),
            shell_deny=_strings(data.get("shell_deny"), "shell_deny"),
            write_paths=(
                None if data.get("write_paths") is None else _strings(data["write_paths"], "paths")
            ),
            rules=_verdicts(data.get("rules")),
            caveats=_caveats(data.get("caveats")),
        )


def narrow(policy: Policy, want: Narrowing) -> Policy | str:
    """The tightened policy, or one line naming the field that tried to loosen."""
    # 1. The mode, along one road only.
    mode = policy.mode
    if want.mode is not None:
        if want.mode not in MODES:
            return f"{want.mode!r} is not a mode"
        if MODES.index(want.mode) < MODES.index(policy.mode):
            return f"{want.mode!r} is looser than {policy.mode!r}"
        mode = want.mode
    # 2. Denied commands are added to; never taken away.
    shell_deny = (*policy.shell_deny, *(p for p in want.shell_deny if p not in policy.shell_deny))
    # 3. Writable paths may only shrink, and only to patterns already allowed.
    write_paths = policy.write_paths
    if want.write_paths is not None:
        extra = [p for p in want.write_paths if p not in policy.write_paths]
        if extra:
            return f"write_paths adds {extra}, which is not a narrowing"
        write_paths = tuple(want.write_paths)
    # 4. A per-tool verdict may only get stricter, and may never be "allow".
    rules = dict(policy.rules)
    for tool, verdict in want.rules.items():
        if verdict == "allow":
            return f"{tool}: a narrowing never says allow"
        if verdict not in VERDICTS:
            return f"{tool}: {verdict!r} is not a verdict"
        if VERDICTS.index(verdict) < VERDICTS.index(rules.get(tool, "allow")):
            return f"{tool}: {verdict!r} is looser than {rules[tool]!r}"
        rules[tool] = verdict
    # 5. The same property again, stated simply, over the answer this function built.
    tightened = replace(
        policy, mode=mode, shell_deny=shell_deny, write_paths=write_paths, rules=rules
    )
    if not is_narrowing(tightened, policy):
        return "the result would not have been a narrowing"
    return tightened


def is_narrowing(new: Policy, old: Policy) -> bool:
    """Is `new` at least as strict as `old` in all four fields? Written once, used
    both as narrow()'s own last check and as what the property test asserts."""
    return (
        new.mode in MODES
        and MODES.index(new.mode) >= MODES.index(old.mode)
        and set(new.shell_deny) >= set(old.shell_deny)
        and set(new.write_paths) <= set(old.write_paths)
        and all(
            VERDICTS.index(v) >= VERDICTS.index(old.rules.get(tool, "allow"))
            for tool, v in new.rules.items()
            if v in VERDICTS
        )
        and all(tool in new.rules for tool in old.rules)
    )


def _mode(value: object) -> str | None:
    # A name that is not a mode is refused now; whether a real mode is *looser*
    # than the current one is narrow()'s question, because only it knows the policy.
    if value is None:
        return None
    if not isinstance(value, str) or value not in MODES:
        raise _bad(f"mode must be one of {', '.join(MODES)}")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise _bad(f"{name} must be a list of strings")
    return tuple(str(v) for v in value)


def _verdicts(value: object) -> Mapping[str, str]:
    # "allow" is refused here rather than in narrow(), because whether it widens
    # does not depend on the current policy: a narrowing that says allow is not a
    # narrowing at all. narrow() checks it again anyway, for a Narrowing built in
    # code rather than read from a proposal.
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _bad("rules must be a table of tool -> ask | deny")
    rules = {str(k): str(v) for k, v in value.items()}
    bad = sorted(f"{tool}: {v!r}" for tool, v in rules.items() if v not in ("ask", "deny"))
    if bad:
        raise _bad(f"a narrowing says ask or deny, never allow ({', '.join(bad)})")
    return rules


def _caveats(value: object) -> tuple[str, ...]:
    # Validated here, against the same parser --scope uses, so a malformed pair is
    # a rejected proposal rather than an exception escaping into the turn. Imported
    # lazily: broker is its own removable package, and a proposal with no caveats
    # field never needs it at all [NFR-12].
    if value is None:
        return ()
    pairs = _strings(value, "caveats")
    try:
        from edgar.broker.caveats import parse_scope
        from edgar.core.errors import ConfigError
    except ModuleNotFoundError as exc:
        raise _bad("caveats: the capability broker is not in this build") from exc
    try:
        parse_scope(pairs)
    except ConfigError as exc:
        raise _bad(str(exc)) from exc
    return pairs


def _bad(message: str) -> Exception:
    # The type parse() catches, so a bad narrowing is one more rejected proposal.
    return Malformed(message)
