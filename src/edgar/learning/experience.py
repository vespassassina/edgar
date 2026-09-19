"""What each run did, recorded from the bus so nothing has to be re-derived [MEM-18]."""

# One run is one main-loop turn, assembled from events and written once:
#
#   PromptTyped      a human typed a line: a new record opens here
#   SkillsActivated  the skills this turn loaded
#   ToolProposed     a call's arguments, read only for the file path they name
#   ToolFinished     one call: its name, and whether it failed
#   VerifyFinished   the declared check's result [VER-7]
#   TurnFinished     cost and reason; the record is written here and closed
#
# Verification is "passed" or "failed" only when the check actually ran. A turn
# that simply stopped is "unverified": a model saying it is done is not a
# verification, so there is no third way to reach "passed" [VER-7].
#
# Subagent events (depth > 0) are skipped. A subagent's turns belong to the run
# that asked for them; counting them again would double every fan-out [SUB-3].
#
# The `errors` table lives here too, beside the runs, because error_facts.py counts
# repeats of the same failure and one project has one learning database.

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from edgar.core.events import (
    Event,
    PromptTyped,
    SkillsActivated,
    TextDelta,
    ToolFinished,
    ToolProposed,
    TurnFinished,
    VerifyFinished,
)
from edgar.memory.redact import redact
from edgar.storage.db import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, at REAL NOT NULL, session TEXT NOT NULL, prompt TEXT NOT NULL,
    tools TEXT NOT NULL, paths TEXT NOT NULL, failures INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL, cost REAL, outcome TEXT NOT NULL, verification TEXT NOT NULL,
    skills TEXT NOT NULL, shape TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS errors (
    scope TEXT NOT NULL, key TEXT NOT NULL, tool TEXT NOT NULL, kind TEXT NOT NULL,
    program TEXT, exit_code INTEGER, seen INTEGER NOT NULL, saved INTEGER NOT NULL,
    PRIMARY KEY (scope, key));
"""


def shape_of(agent: str, tools: Sequence[str]) -> str:
    """What counts as "the same task shape". Resolves OQ-6 [SKL-8d].

    The agent, then the distinct tool names in the order they were first called.
    Order is part of it because reading then editing is a different job from editing
    then reading. Routing tags, which OQ-6 also named, are left out: nothing in edgar
    sets a tag yet, so including one would only ever add an empty string.

    It lives here rather than in synthesis.py because this is the module that stores
    a shape, and one definition is what lets `edgar stats` and the repeat trigger
    agree about what recurred.
    """
    # A readable string rather than OQ-6's hash: it is short, it is what `edgar
    # stats` prints under "shapes", and a person can tell two of them apart.
    ordered = ">".join(dict.fromkeys(tools)) or "answer"
    return f"{agent or 'main'}:{ordered}"


@dataclass(slots=True)
class Run:
    """One turn as it happens; the Recorder fills it in and writes it once."""

    session: str
    prompt: str  # what the human typed, redacted on the way to disk [MEM-14, MEM-15]
    at: float = field(default_factory=time.time)
    started: float = field(default_factory=time.monotonic)
    tools: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    # What the model answered, kept for history.md's "- said:" line [MEM-13]. It is
    # model-written text: it goes to a file a human reads, never to a fact.
    said: list[str] = field(default_factory=list)
    failures: int = 0
    duration_ms: int = 0
    cost: float | None = None
    outcome: str = "stop"
    verification: str = "unverified"  # passed | failed | unverified [VER-7]

    @property
    def shape(self) -> str:
        """Two runs of the same shape did the same kind of work, which is what makes
        the shape worth storing at all. A main-loop run is the only kind recorded, so
        the agent is always the main one [OQ-6]."""
        return shape_of("", self.tools)


@dataclass(frozen=True, slots=True)
class Stats:
    runs: int
    since: float
    verification: dict[str, int]
    with_failures: int
    cost: float
    tools: list[tuple[str, int]]
    shapes: list[tuple[str, int]]


class Experience(Store):
    schema = SCHEMA

    def record(self, run: Run) -> None:
        self._write(
            "INSERT INTO runs (at, session, prompt, tools, paths, failures, duration_ms,"
            " cost, outcome, verification, skills, shape) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            run.at,
            run.session,
            redact(run.prompt),
            " ".join(run.tools),
            " ".join(run.paths),
            run.failures,
            run.duration_ms,
            run.cost,
            run.outcome,
            run.verification,
            " ".join(run.skills),
            run.shape,
        )

    def stats(self) -> Stats:
        """Everything `edgar stats` prints, from one pass over the rows [MEM-19]."""
        # A run's row is a handful of short strings, so counting them in Python is
        # cheaper to read than six GROUP BYs and fast enough for any real project.
        rows = self._rows(
            "SELECT at, verification, failures, cost, tools, shape FROM runs ORDER BY at"
        )
        tools: Counter[str] = Counter()
        shapes: Counter[str] = Counter()
        verdicts: Counter[str] = Counter()
        cost, failed = 0.0, 0
        for _, verdict, failures, run_cost, names, shape in rows:
            verdicts[str(verdict)] += 1
            shapes[str(shape)] += 1
            tools.update(str(names).split())
            cost += float(run_cost or 0.0)
            failed += 1 if failures else 0
        return Stats(
            runs=len(rows),
            since=float(rows[0][0]) if rows else 0.0,
            verification=dict(verdicts),
            with_failures=failed,
            cost=cost,
            tools=tools.most_common(5),
            shapes=shapes.most_common(5),
        )

    def shape_count(self, shape: str) -> int:
        """How many recorded runs did this kind of work, the repeat trigger's one
        question [SKL-8d]. Rows only: a shape nobody ran is zero, not an error."""
        rows = self._rows("SELECT COUNT(*) FROM runs WHERE shape = ?", shape)
        return int(rows[0][0]) if rows else 0

    def seen(self, scope: str, key: str, record: dict[str, Any]) -> tuple[int, bool]:
        """Count one more sighting of the same failure; return the count and whether
        a fact was already saved for it [MEM-22]."""
        self._write(
            "INSERT INTO errors (scope, key, tool, kind, program, exit_code, seen, saved)"
            " VALUES (?,?,?,?,?,?,1,0) ON CONFLICT (scope, key) DO UPDATE SET seen = seen + 1",
            scope,
            key,
            record["tool"],
            record["kind"],
            record["program"],
            record["exit_code"],
        )
        rows = self._rows("SELECT seen, saved FROM errors WHERE scope = ? AND key = ?", scope, key)
        return (int(rows[0][0]), bool(rows[0][1])) if rows else (0, True)

    def mark_saved(self, scope: str, key: str) -> None:
        self._write("UPDATE errors SET saved = 1 WHERE scope = ? AND key = ?", scope, key)


class Recorder:
    """The bus subscriber that turns one turn's events into one row [MEM-18]."""

    def __init__(
        self, store: Experience, *, session: str, sinks: Sequence[Callable[[Run], None]] = ()
    ) -> None:
        self.store, self.session, self.sinks = store, session, sinks
        self.run: Run | None = None

    def __call__(self, event: Event) -> None:
        # 1. A subagent's events belong to the run that spawned it, not to a run.
        if event.depth:
            return
        # 2. A typed line opens a record. Nothing else can open one, so a run
        #    always starts from something a human asked for.
        if isinstance(event, PromptTyped):
            self.run = Run(session=self.session, prompt=event.text)
            return
        run = self.run
        if run is None:
            return
        # 3. Everything after it fills the open record in.
        if isinstance(event, SkillsActivated):
            run.skills = list(event.names)
        elif isinstance(event, TextDelta) and len("".join(run.said)) < 400:
            run.said.append(event.text)
        elif isinstance(event, ToolProposed):
            run.paths.extend(_path(event.args_preview))
        elif isinstance(event, ToolFinished):
            run.tools.append(event.tool)
            run.failures += 0 if event.ok else 1
        elif isinstance(event, VerifyFinished):
            run.verification = "passed" if event.ok else "failed"
        elif isinstance(event, TurnFinished):
            self.close(event)

    def close(self, event: TurnFinished) -> None:
        # 4. The turn is over: finish the record, store it, hand it to the sinks.
        run = self.run
        if run is None:
            return
        run.duration_ms = round((time.monotonic() - run.started) * 1000)
        run.cost, run.outcome, self.run = event.cost, event.reason, None
        self.store.record(run)
        for sink in self.sinks:
            sink(run)


def _path(preview: str) -> list[str]:
    # The file a call names, taken from the arguments the pipeline already
    # previewed. Only a "path" key, because that is the one every file tool uses;
    # a preview cut at its length limit is not JSON any more and names nothing.
    try:
        args = json.loads(preview)
    except ValueError:
        return []
    value = args.get("path") if isinstance(args, dict) else None
    return [value] if isinstance(value, str) else []
