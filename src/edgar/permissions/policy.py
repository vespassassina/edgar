# The permission decision: one pure function
# [PERM-1..5, PERM-11, PERM-12, PERM-14, PERM-16].
#
# Everything that needs I/O (resolving paths, loading grants, asking the user) is
# done by the caller, permissions/guard.py. What is left can be tested
# exhaustively. First match wins:
#
# 1. the hard layer, which no rule or grant overrides: catastrophic commands, a
#    literal link-local URL (cloud metadata), credentials, control files, and
#    anything outside the working directory
# 2. an explicit per-tool rule from config, then a grant a human gave
# 3. the mode's default, tightened by taint in auto; remember only proposes a
#    fact a human confirms later, so it needs no prompt outside read-only [MEM-21]
# 4. the tool's own dangerous flag, which turns an allow into an ask

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from edgar.permissions import matcher
from edgar.permissions.matcher import Subject
from edgar.tools.base import ToolSchema

MODES = ("read-only", "ask", "auto", "yolo")  # [PERM-1]


@dataclass(frozen=True, slots=True)
class Allow:
    source: str = "mode"


@dataclass(frozen=True, slots=True)
class Deny:
    reason: str
    source: str = "mode"
    needed_prompt: bool = False  # an Ask with nobody to answer: `-p` exits 5 [PERM-7]


@dataclass(frozen=True, slots=True)
class Ask:
    reason: str
    source: str = "mode"


Decision = Allow | Deny | Ask


@dataclass(frozen=True, slots=True)
class Policy:
    mode: str
    cwd: Path
    home: Path
    interactive: bool = False
    tainted: bool = False  # [PERM-11]
    rules: Mapping[str, str] = field(default_factory=dict)  # tool → allow | ask | deny
    grants: frozenset[tuple[str, str]] = frozenset()  # (tool, subject) a human allowed
    write_paths: tuple[str, ...] = ("./**",)  # [PERM-3]
    shell_allow: tuple[str, ...] = ()
    shell_deny: tuple[str, ...] = ()
    control: Callable[[Path], bool] = lambda path: False  # [PERM-12]


def category(tool: ToolSchema) -> str:
    # Command tools marked read_only count as reads; everything else as declared.
    return "read" if tool.read_only and tool.kind == "command" else tool.category


def decide(tool: ToolSchema, subject: Subject, p: Policy) -> Decision:
    decision = _decide(tool, subject, p)
    if isinstance(decision, Ask) and not p.interactive:
        return Deny(f"{decision.reason}, and nobody is here to answer", decision.source, True)
    return decision


def _decide(tool: ToolSchema, s: Subject, p: Policy) -> Decision:
    kind = category(tool)
    commands = matcher.segments(s.command) if s.command else []
    # 1. The hard layer.
    if any(matcher.matches(c, matcher.CATASTROPHIC) for c in commands):
        return Deny(f"{s.text!r} is never run", "hard")
    if kind == "network" and matcher.link_local(s.text):
        return Deny(f"{s.text} names a link-local address", "hard")  # [PERM-16]
    if p.mode == "yolo":
        return Allow("mode")
    if s.path is not None:
        if matcher.credential(s.path, p.home):
            return Deny(f"{s.text} holds credentials", "hard")
        if kind == "write" and p.control(s.path):
            return Ask(f"{s.text} is a control file: it steers edgar itself", "control")
        if not matcher.inside(s.path, p.cwd) and (tool.name, s.text) not in p.grants:
            return Ask(f"{s.text} is outside the working directory", "hard")
    # 2. Rules and grants: decisions a human made.
    rule = p.rules.get(tool.name)
    if rule == "deny" or any(matcher.matches(c, p.shell_deny) for c in commands):
        return Deny(f"denied by [permissions] for {tool.name}", "rule")
    if rule == "allow":
        return Allow("rule")
    if rule == "ask":
        return Ask(f"[permissions] says ask for {tool.name}", "rule")
    if (tool.name, s.text) in p.grants:
        return Allow("grant")
    # 3 and 4. The mode, then the tool's own flag.
    decision = _mode(kind, s, commands, p)
    if isinstance(decision, Allow) and tool.dangerous:
        return Ask(f"{tool.name} is marked dangerous", "tool")
    return decision


def network_allowed(mode: str, tainted: bool) -> bool:
    # Whether a confined process may reach the network [PERM-15, PERM-11].
    #
    # A sandbox enforces, it does not decide, so the answer is made here and carried
    # to it. It mirrors _decide on the same inputs: yolo allows before anything
    # else is read, read-only never reaches out on its own, and a session that has
    # taken in untrusted content does not either.
    return mode == "yolo" or (mode != "read-only" and not tainted)


def _mode(kind: str, s: Subject, commands: list[str], p: Policy) -> Decision:
    if kind == "read":
        return Allow()
    # `remember` only writes a pending fact; the human gate is at the turn's end [MEM-21].
    if kind == "memory" and p.mode != "read-only":
        return Allow()
    listed = bool(commands) and all(matcher.matches(c, p.shell_allow) for c in commands)
    allowed = listed and not matcher.substitutes(s.command or "")  # never auto-allow $(…)
    if p.mode == "read-only":
        if kind == "network":
            return Ask("network access in read-only mode")
        return Deny(f"{kind} tools are off in read-only mode")
    if p.mode == "ask":
        return Allow("rule") if kind == "shell" and allowed else Ask(f"{kind}: {s.text}")
    # auto
    if kind == "write":
        if s.path is not None and matcher.within(s.path, p.cwd, p.write_paths):
            return Allow()
        return Ask(f"{s.text} is outside [permissions] write_paths")
    if p.tainted and not allowed:
        return Ask(f"{kind} after reading untrusted content", "taint")
    if kind == "shell" and matcher.substitutes(s.command or ""):
        return Ask("command substitution is never auto-allowed")
    return Allow()
