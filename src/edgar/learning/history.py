"""`history.md`: what happened, in a file a person can read [MEM-12..17]."""

# One entry per run, appended, never rewritten:
#
#   ## 2026-09-17T14:22:31 · session 0f3a1c · $0.0142
#   - asked: fix the failing import in the cli
#   - said: moved the import inside main() so startup stays under budget
#   - did: read, edit, shell
#   - files: src/edgar/cli/main.py
#   - outcome: stop · verification passed
#
# Three rules hold it together:
#
#   redaction    every entry goes through redact() before it is written, and
#                `--no-history` or `[memory] history = false` skips the file
#                entirely [MEM-15]
#   rotation     over CAP bytes the file moves to history.1.md and a new one
#                starts, so it never grows without bound [MEM-16]
#   condensing   a prompt past WORDS words is cut to its first WORDS and says how
#                many were left out. The whole prompt stays in learning.db, so
#                nothing is lost by the file being short [MEM-14]
#
# The `- said:` line is text the model wrote. That is the reason distill() below
# may only ever produce pending facts: a history file is not a safe source, and a
# human confirms every fact that comes out of one [MEM-17, ADR-0017].

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from edgar.learning.experience import Run
from edgar.memory.redact import redact
from edgar.memory.store import Fact, Memory

CAP = 256 * 1024  # bytes, before rotation [MEM-16]
WORDS = 200  # a prompt longer than this is condensed in the file [MEM-14]
KEEP = 40  # how many of its words the entry keeps
LEAST = 3  # how often something must recur before distill() proposes it


def condense(prompt: str) -> str:
    """A long prompt, shortened for the file. The verbatim one is in SQLite."""
    words = prompt.split()
    if len(words) <= WORDS:
        return " ".join(words)
    return " ".join(words[:KEEP]) + f" … ({len(words) - KEEP} more words; see `edgar stats`)"


def entry(run: Run) -> str:
    """One run as the lines it is worth reading back [MEM-13]."""
    when = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(run.at))
    cost = "cost unknown" if run.cost is None else f"${run.cost:.4f}"
    lines = [
        f"## {when} · session {run.session} · {cost}",
        f"- asked: {condense(run.prompt)}",
        f"- said: {' '.join(' '.join(run.said).split())[:200]}",
        f"- did: {', '.join(dict.fromkeys(run.tools)) or 'nothing'}",
        f"- files: {', '.join(dict.fromkeys(run.paths)) or 'none'}",
        f"- outcome: {run.outcome} · verification {run.verification}",
    ]
    return redact("\n".join(lines)) + "\n\n"


class History:
    def __init__(self, path: Path, cap: int = CAP) -> None:
        self.path, self.cap = path, cap

    def append(self, run: Run) -> None:
        # 1. Rotate first, so one entry is never split across two files.
        if self.path.exists() and self.path.stat().st_size >= self.cap:
            self.path.replace(self.path.with_suffix(".1.md"))
        # 2. Append. A history that cannot be written is not worth a failed turn.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry(run))


def entries(path: Path) -> list[str]:
    """The file's entries, newest last, for `edgar history show`."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [("## " + part).rstrip() for part in text.split("## ") if part.strip()]


def distill(path: Path, memory: Memory, scope: str) -> list[Fact]:
    """Reprocess history into **pending** facts for `memory review` [MEM-17]."""
    # 1. Count what recurs, from the two structured lines. The prose lines are
    #    deliberately not read: they are the model's, and so is their judgement.
    files: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    for line in "\n".join(entries(path)).splitlines():
        if line.startswith("- files: ") and line != "- files: none":
            files.update(part.strip() for part in line[9:].split(","))
        elif line.startswith("- did: ") and line != "- did: nothing":
            shapes[line[7:].strip()] += 1
    total = sum(shapes.values())
    # 2. One proposal per thing that recurs often enough to be worth a human's
    #    attention, phrased as the observation it is.
    proposals = [
        f"work in this project usually touches {name} ({count} of {total} runs)"
        for name, count in files.most_common(3)
        if count >= LEAST
    ]
    proposals += [
        f"runs in this project usually use {name} ({count} of {total} runs)"
        for name, count in shapes.most_common(2)
        if count >= LEAST
    ]
    # 3. Pending, always. `distill` has no way to make an active fact: the store
    #    puts anything whose provenance is not on the safe list into `pending`,
    #    and "distilled" is not on it [MEM-17, ADR-0017].
    return [memory.add(text, scope, provenance="distilled") for text in proposals]
