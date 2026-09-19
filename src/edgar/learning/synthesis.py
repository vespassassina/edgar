"""When a run is worth keeping, and what may be read while keeping it [SKL-8..12, SKL-16]."""

# A skill is instructions that future sessions follow. Writing one from a session
# that may itself have been steered by a hostile page is the failure this whole file
# is arranged around, so it is built the way M12 built the learner: subscribe
# narrowly, carry nothing that could launder untrusted text, and let the *types*
# enforce it rather than a filter.
#
# The flow, driven by controller/gate.py after a turn ends:
#
#   1. the gate has counted the turn        tools, failures, the declared check
#   2. triggers(turn, config, store)        arithmetic: which of SKL-8's four fired?
#   3. nothing fired                        stop here: no call, no cost
#   4. Outline.of(turn, names).render()     the ONLY text the synthesiser is given
#   5. one model call, no tools             answers with a propose_skill object
#   6. write_learned() or a proposal file   auto writes; propose leaves it to a human
#
# What step 4 may carry, and nothing else [SKL-9]:
#
#   the line a human typed          PromptTyped, the one safe road [MEM-8]
#   corrections a human typed       /steer, also typed by a human
#   tool NAMES, in call order       chosen by the model, but a name from a fixed set
#   ErrorRecords                    four fields the harness computed [MEM-22]
#   the verification result         passed | failed | unverified [VER-7]
#
# Tool arguments are deliberately NOT in that list, though SKL-9 allows them. An
# argument is model-written text composed after the model read the previous tool's
# output, so "copy the file you just read into the next call's argument" is a way to
# launder tool output into a skill. Names are a closed vocabulary; arguments are not.
# The M14 ADR carries the argument.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from edgar.config.schema import SkillsSection
from edgar.core.message import ErrorRecord
from edgar.learning.experience import Experience, shape_of
from edgar.memory.redact import redact
from edgar.skills.discovery import BODY_SECTIONS, LEARNED, body_shape, discover

# The same strip error_facts.py applies to a program name, spelled again rather
# than imported: that module reaches memory/store.py, and the controller that
# calls this one may not [ADR-0017, test_controller_boundary.py].
UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# What the synthesiser is told. Like the controller's BRIEF this is a prompt, not a
# policy: every rule in it is also enforced in code, because a prompt is advice and
# write_learned() is the wall.
BRIEF = f"""You are writing one reusable skill from the outline of one run of an
agent. A skill is instructions a future session will follow. Answer with one JSON
object and nothing else:

{{"action": "propose_skill", "name": "lowercase-with-dashes", "body": "...",
 "reason": "one short sentence"}}

The body is Markdown with exactly these four headings, in this order, and nothing
above the first one:

{chr(10).join("## " + name for name in BODY_SECTIONS)}

Write the general procedure, not this run's specifics: no file names that were
only true today, no versions, no paths. "When to use" opens with one sentence
saying when a future session should reach for this, because that sentence becomes
the skill's description. If the run is too ordinary to be worth a skill, answer
{{"action": "noop", "reason": "why not"}}."""


@dataclass(frozen=True, slots=True)
class Turn:
    """One finished turn, in the only terms synthesis may see [SKL-9].

    There is no field here for a tool's output, an error's text or a fetched page,
    and that absence is the security property: `render()` cannot leak what `Turn`
    cannot hold. Adding a field is therefore an ADR, not a patch.
    """

    prompt: str = ""  # the line a human typed [MEM-8]
    corrections: tuple[str, ...] = ()  # lines a human typed while it ran (/steer)
    tools: tuple[str, ...] = ()  # tool names, in call order; never their arguments
    errors: tuple[ErrorRecord, ...] = ()  # four harness-computed fields each [MEM-22]
    verification: str = "unverified"  # passed | failed | unverified [VER-7]
    agent: str = ""  # "" is the main loop; a subagent names itself
    skills: tuple[str, ...] = ()  # skills this turn already loaded


def triggers(turn: Turn, config: SkillsSection, store: Experience) -> tuple[str, ...]:
    """Which of SKL-8's four deterministic checks this turn fires, in a fixed order.

    Pure but for one read: trigger (d) counts rows in the experience store, which is
    the only way to know a shape recurred *across sessions*. Everything else is the
    turn itself.
    """
    # 1. Three of the four want the declared check to have passed. A model saying it
    #    is done is not a verification, so there is no other way to get here [VER-7].
    verified = turn.verification == "passed"
    fired = []
    if verified and len(turn.tools) >= config.min_tool_calls:
        fired.append("long")
    if verified and turn.errors:
        fired.append("recovered")
    # 2. A correction does not wait for a check: a human saying "no, like this" is a
    #    statement about the procedure, whatever the run then did [SKL-8c].
    if turn.corrections:
        fired.append("correction")
    # 3. The repeat, only when no skill already covers the work: a turn that loaded a
    #    skill is a turn whose procedure is written down already [SKL-8d].
    if verified and not turn.skills and _repeats(turn, store) >= config.min_repeats:
        fired.append("repeated")
    return tuple(fired)


def _repeats(turn: Turn, store: Experience) -> int:
    return store.shape_count(shape_of(turn.agent, turn.tools))


@dataclass(frozen=True, slots=True)
class Outline:
    """The run as the synthesiser sees it: names, counts and typed text [SKL-9]."""

    tripped: tuple[str, ...]
    prompt: str = ""
    corrections: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()  # "shell nonzero_exit exit 1 (pytest)" — no message
    verification: str = "unverified"
    shape: str = ""

    @classmethod
    def of(cls, turn: Turn, tripped: tuple[str, ...]) -> Outline:
        # Everything is copied through a narrowing: the ErrorRecords become the four
        # fields spelled out, and the typed lines are redacted the way anything
        # bound for a file or a prompt is [MEM-15].
        return cls(
            tripped=tripped,
            prompt=redact(turn.prompt),
            corrections=tuple(redact(line) for line in turn.corrections),
            tools=turn.tools,
            errors=tuple(_error(record) for record in turn.errors),
            verification=turn.verification,
            shape=shape_of(turn.agent, turn.tools),
        )

    def render(self) -> str:
        lines = [
            f"what tripped: {', '.join(self.tripped)}",
            f"what was asked: {self.prompt}",
            f"tools called, in order: {', '.join(self.tools) or 'none'}",
            f"failures the harness recorded: {'; '.join(self.errors) or 'none'}",
            f"declared check: {self.verification}",
            f"task shape: {self.shape}",
        ]
        if self.corrections:
            lines.append("corrections typed during the run: " + " | ".join(self.corrections))
        return "\n".join(lines)


def _error(record: ErrorRecord) -> str:
    # The four fields, never the message. `program` is a basename the model chose,
    # so it is stripped to [A-Za-z0-9._-] here, the same strip error_facts.py does
    # before templating a fact. The tool pipeline strips it too; doing it twice is
    # cheaper than the day one of the two paths stops [MEM-22].
    code = f" exit {record.exit_code}" if record.exit_code is not None else ""
    program = UNSAFE.sub("", record.program or "")
    return f"{UNSAFE.sub('', record.tool)} {record.kind}{code}" + (
        f" ({program})" if program else ""
    )


@dataclass(frozen=True, slots=True)
class Provenance:
    """The frontmatter a learned skill carries, so nobody has to guess [SKL-12]."""

    session: str
    trigger: str
    created: str = field(default="")


def render_skill(name: str, body: str, *, session: str, trigger: str, created: str) -> str:
    """One `SKILL.md`: provenance frontmatter, then the body the model wrote."""
    # The description is the first sentence under "When to use", not a separate
    # field the model could forget: the body shape guarantees the heading is there,
    # so there is always something to take. discovery.read() needs it non-empty.
    description = _description(body) or f"a procedure learned from session {session}"
    head = "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {description}",
            "learned: true",
            f"session: {session}",
            f"trigger: {trigger}",
            f"created: {created}",
            "---",
        ]
    )
    return f"{head}\n\n{body.strip()}\n"


def _description(body: str) -> str:
    # The first non-empty line after "## When to use", trimmed to what a
    # frontmatter line can hold. YAML would choke on a colon, so it is quoted.
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "## When to use":
            after = [text.strip() for text in lines[index + 1 :] if text.strip()]
            first = after[0][:300] if after else ""
            return f'"{first.replace(chr(34), "")}"' if first else ""
    return ""


def write_learned(
    root: Path, home: Path, name: str, body: str, *, session: str, trigger: str, created: str = ""
) -> Path | str:
    """Write one learned skill, or say in a sentence why it was not written.

    The only path in edgar that creates a skill file. It refuses far more often than
    it writes, and each refusal is a rule from SKL-11 or SKL-16 [CTRL-13].
    """
    # 1. The body has to have the four sections. A skill that does not say when to
    #    use it or how to check it is not a skill [SKL-16].
    wrong = body_shape(body)
    if wrong is not None:
        return f"refused {name}: {wrong}"
    # 2. A hand-authored skill of this name is never touched, in any mode. Discovery
    #    is the one that knows which is which, and it is the one asked [SKL-11].
    existing = discover(root, home).skills.get(name)
    if existing is not None and not existing.origin.endswith("learned"):
        where = existing.path.relative_to(root).as_posix() if _under(existing.path, root) else name
        return f"refused {name}: a hand-authored skill has that name ({where})"
    # 3. Inside `learned/` and nowhere else. The path is built from the slug
    #    proposals.py already checked, so it cannot climb out of the folder.
    path = root.joinpath(*LEARNED.split("/"), name, "SKILL.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_skill(name, body, session=session, trigger=trigger, created=created),
        encoding="utf-8",
    )
    return path


def _under(path: Path, root: Path) -> bool:
    # relative_to() raises rather than answering, and a user-scope skill really is
    # outside the project, so the question is asked before it is used.
    return root.resolve() in path.resolve().parents
