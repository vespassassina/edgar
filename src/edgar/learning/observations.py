"""Skills improve in use: what a turn noticed, and the patch it eventually earns [SKL-6, SKL-14]."""

# A skill that is followed and then goes wrong is the cheapest teacher edgar has.
# So a turn that loaded one and ended badly leaves a line behind, and enough lines
# earn one model call that proposes a better body.
#
# The flow, driven by controller/gate.py in the same post-turn step as synthesis:
#
#   1. the turn loaded skills          SkillsActivated named them
#   2. and it ended badly              errors, a correction, or a failed check
#   3. observe(...)                    one redacted line per skill, appended
#   4. enough lines                    >= skills.distill_after, default 3
#   5. outline(name, body, notes)      the current body and the lines, nothing else
#   6. one model call, no tools        answers with a propose_skill, same as synthesis
#   7. write_learned() or a proposal   SKL-10 and SKL-11 decide, exactly as before
#
# Where the lines live is the one decision worth reading twice. SKL-14 says "that
# skill's HISTORY.md", which for a hand-authored skill would mean edgar writing
# inside a folder a person owns. It does not: every observation goes to one
# machine-owned folder, one file per skill name, whatever the skill's origin. A
# hand-authored skill is still observed and still gets patches proposed; what
# changes is that nothing edgar writes ever lands beside a file you wrote. The M14
# ADR carries the argument.

from __future__ import annotations

from pathlib import Path

from edgar.core.message import ErrorRecord
from edgar.memory.redact import redact
from edgar.skills.discovery import BODY_SECTIONS

HISTORY = ".edgar/skills/learned/.history"  # machine-owned, per PRD §9.5

PATCH_BRIEF = f"""A skill was followed and the runs did not go well. Rewrite its
body so the next run goes better. Answer with one JSON object and nothing else:

{{"action": "propose_skill", "name": "SAME-NAME", "body": "...",
 "reason": "one short sentence"}}

Keep the name. The body is Markdown with exactly these four headings, in order:

{chr(10).join("## " + name for name in BODY_SECTIONS)}

Change what the observations point at and leave the rest alone. If they do not
say anything actionable, answer {{"action": "noop", "reason": "why not"}}."""


def observe(
    root: Path,
    name: str,
    *,
    errors: tuple[ErrorRecord, ...],
    corrections: tuple[str, ...],
    verification: str,
) -> int:
    """Append one line about one skill's bad turn, and say how many there are now.

    Returns 0 when the turn was unremarkable, so the caller's next step is a plain
    comparison against `skills.distill_after` [SKL-14].
    """
    # 1. Only a turn that went wrong is worth a line. A skill that worked is a
    #    skill nobody needs to hear about.
    note = _note(errors, corrections, verification)
    if not note:
        return 0
    # 2. One file per skill, in the machine-owned folder, appended never rewritten.
    path = root.joinpath(*HISTORY.split("/")) / f"{_slug(name)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {note}\n")
    return len(notes(root, name))


def _note(errors: tuple[ErrorRecord, ...], corrections: tuple[str, ...], verification: str) -> str:
    # The same closed vocabulary synthesis.py works in: computed error fields, the
    # check's verdict, and lines a human typed, redacted [SKL-9, MEM-15]. There is
    # no branch here that could reach a tool's output, because nothing passes one.
    parts = []
    if verification == "failed":
        parts.append("the declared check failed")
    if errors:
        kinds = sorted({f"{record.tool} {record.kind}" for record in errors})
        parts.append("failures: " + ", ".join(kinds))
    if corrections:
        parts.append("corrected: " + " | ".join(redact(line) for line in corrections if line))
    return "; ".join(parts)


def notes(root: Path, name: str) -> tuple[str, ...]:
    """Every observation recorded for one skill, oldest first."""
    path = root.joinpath(*HISTORY.split("/")) / f"{_slug(name)}.md"
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(line[2:] for line in lines if line.startswith("- "))


def outline(name: str, body: str, recorded: tuple[str, ...]) -> str:
    """The whole of what the distiller is given: the skill, and what went wrong."""
    # The body is text edgar has already accepted into the index, and the notes are
    # built by _note() above. Neither can carry a tool's output.
    return "\n".join([f"skill: {name}", "", body.strip(), "", "observations:", *recorded])


def _slug(name: str) -> str:
    # A skill name is already [a-z0-9-] by the time discovery accepts it, but this
    # builds a file name, so it is not trusted to be: anything else is dropped.
    kept = "".join(c for c in name.lower() if c.isalnum() or c == "-")
    return kept[:60] or "unnamed"
