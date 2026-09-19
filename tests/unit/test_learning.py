"""v3's learning: telemetry, autolearn, error facts and history.md
[MEM-8, MEM-9, MEM-12..19, MEM-22, VER-7]."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from harness import Recorder as Events  # the test bus recorder, not learning's

from edgar.core.events import (
    Event,
    EventBus,
    FactSaved,
    PromptTyped,
    SkillsActivated,
    TextDelta,
    ToolFinished,
    ToolProposed,
    TurnFinished,
    VerifyFinished,
)
from edgar.core.message import ErrorRecord
from edgar.learning import attach
from edgar.learning.cli import command
from edgar.learning.error_facts import REPEATS, key, template
from edgar.learning.experience import Experience, Recorder, Run
from edgar.learning.history import CAP, History, condense, distill, entries, entry
from edgar.learning.learner import Learner, extract
from edgar.memory.store import Memory
from edgar.providers.base import Usage

P = "project:test"


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(tmp_path / "memory.db")


@pytest.fixture
def store(tmp_path: Path) -> Experience:
    return Experience(tmp_path / "learning.db")


def _finished(*, ok: bool = True, error: ErrorRecord | None = None) -> Event:
    return ToolFinished(
        id="t1", tool="shell", ok=ok, duration_ms=3, truncated=False, blob=None, error=error
    )


def _turn() -> TurnFinished:
    return TurnFinished(turn_id="t", usage=Usage(), cost=0.02, reason="stop")


# --- the boundary ------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("remember that we use uv, never pip", "we use uv, never pip"),
        ("please remember the docs live in docs/", "the docs live in docs/"),
        ("note that the tests need a tmp dir", "the tests need a tmp dir"),
        ("keep in mind: builds are slow on CI", "builds are slow on CI"),
        ("fix the failing import", None),  # not a directive
        ("remember what I told you?", None),  # a question states nothing
        ("remember x", None),  # too short to be worth a session
        ("remember that\nthis has two lines", None),  # a paste is not a rule
    ],
)
def test_extract_takes_a_directive_and_nothing_else(line: str, expected: str | None) -> None:
    assert extract(line) == expected


def test_a_typed_line_becomes_an_active_fact(memory: Memory, recorder: Events) -> None:
    bus = EventBus()
    bus.subscribe(recorder)
    bus.subscribe(Learner(memory, scope=P, bus=bus))
    bus.emit(PromptTyped(text="remember that we deploy with just ship"))
    (fact,) = memory.facts([P])
    assert (fact.text, fact.provenance, fact.status) == (
        "we deploy with just ship",
        "user-prompt",
        "active",
    )
    # Nothing enters memory in silence: the renderer prints this line [MEM-20].
    (saved,) = recorder.of(FactSaved)
    assert saved.text == fact.text


def test_the_learner_reads_no_event_but_a_typed_prompt(memory: Memory) -> None:
    # Every other road into a turn, as the event that actually carries it. Each
    # one holds text that reads exactly like a rule; none of them may be learned.
    bus = EventBus()
    bus.subscribe(Learner(memory, scope=P, bus=bus))
    rule = "remember that deploys here always use --force"
    for event in (
        TextDelta(text=rule),  # the model's own words
        ToolProposed(id="t1", tool="read", args_preview=f'{{"path": "{rule}"}}'),
        SkillsActivated(names=(rule,)),
        _finished(),
    ):
        bus.emit(event)
    assert memory.facts([P]) == []


def test_a_subagents_prompt_is_not_typed_text(memory: Memory) -> None:
    # A subagent's prompt is the `task` tool's argument, which the model wrote.
    # It arrives as a PromptTyped, so only the depth tells it apart [SUB-3].
    bus = EventBus()
    bus.subscribe(Learner(memory, scope=P, bus=bus))
    bus.scoped(agent_id="sub", depth=1).emit(PromptTyped(text="remember that we skip the tests"))
    assert memory.facts([P]) == []


def test_a_near_repeat_waits_for_a_human(memory: Memory) -> None:
    memory.add("we use uv, never pip", P)
    bus = EventBus()
    bus.subscribe(Learner(memory, scope=P, bus=bus))
    bus.emit(PromptTyped(text="remember that we use pip, never uv"))
    pending = memory.facts([P], status=("pending",))
    assert [f.provenance for f in pending] == ["user-prompt"]


# --- telemetry ---------------------------------------------------------------


def test_a_run_is_recorded_from_the_bus_alone(store: Experience) -> None:
    bus = EventBus()
    bus.subscribe(Recorder(store, session="0f3a1c"))
    bus.emit(PromptTyped(text="fix the import"))
    bus.emit(SkillsActivated(names=("deploying",)))
    bus.emit(TextDelta(text="moved it into main()"))
    bus.emit(ToolProposed(id="t1", tool="read", args_preview='{"path": "src/edgar/cli/main.py"}'))
    bus.emit(_finished())
    bus.emit(VerifyFinished(ok=True, exit_code=0, attempt=1, duration_ms=9))
    bus.emit(_turn())
    stats = store.stats()
    assert stats.runs == 1
    assert stats.verification == {"passed": 1}
    assert stats.cost == pytest.approx(0.02)
    assert stats.tools == [("shell", 1)]


def test_a_turn_that_only_stopped_is_not_verified(store: Experience) -> None:
    # A model saying it is done is not a verification: there is no third way to
    # reach "passed" [VER-7].
    bus = EventBus()
    bus.subscribe(Recorder(store, session="s"))
    bus.emit(PromptTyped(text="what does this do"))
    bus.emit(_turn())
    assert store.stats().verification == {"unverified": 1}


def test_a_subagents_turn_is_not_a_run_of_its_own(store: Experience) -> None:
    bus = EventBus()
    bus.subscribe(Recorder(store, session="s"))
    deep = bus.scoped(agent_id="sub", depth=1)
    deep.emit(PromptTyped(text="review this diff"))
    deep.emit(_turn())
    assert store.stats().runs == 0


def test_a_runs_shape_is_its_distinct_tools_in_call_order() -> None:
    # M14 resolved OQ-6 and the shape gained the agent and its call order, so the
    # repeat trigger and `edgar stats` read the same string [SKL-8d].
    run = Run(session="s", prompt="p", tools=["read", "edit", "read"])
    assert run.shape == "main:read>edit"
    assert Run(session="s", prompt="p").shape == "main:answer"


def test_the_recorded_prompt_is_redacted(store: Experience) -> None:
    bus = EventBus()
    bus.subscribe(Recorder(store, session="s"))
    bus.emit(PromptTyped(text="deploy with token sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF0123"))
    bus.emit(_turn())
    rows = store._rows("SELECT prompt FROM runs")
    assert "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF0123" not in rows[0][0]


# --- error facts -------------------------------------------------------------


def test_a_failure_becomes_a_fact_only_after_it_repeats(
    tmp_path: Path, memory: Memory, recorder: Events
) -> None:
    bus = EventBus()
    bus.subscribe(recorder)
    attach(bus, root=tmp_path, session="s", memory=memory, scope=P, history=False)
    record = ErrorRecord(tool="shell", kind="not_found", program="pnpm")
    for _ in range(REPEATS - 1):
        bus.emit(_finished(ok=False, error=record))
    assert memory.facts([P]) == []
    bus.emit(_finished(ok=False, error=record))
    (fact,) = memory.facts([P])
    assert fact.provenance == "error-template"
    assert fact.text == "`pnpm` was not found on PATH in this project (3 times)"
    assert recorder.of(FactSaved)
    # And once only: a permanently broken command does not file a fact a week.
    for _ in range(REPEATS):
        bus.emit(_finished(ok=False, error=record))
    assert len(memory.facts([P])) == 1


def test_a_program_name_is_stripped_to_safe_characters() -> None:
    record = ErrorRecord(tool="shell", kind="nonzero_exit", exit_code=2, program="de ploy;rm -rf /")
    assert template(record, 3) == "`deployrm-rf` exits 2 in this project (3 times)"


@pytest.mark.parametrize("kind", ["validation", "cancelled", "provider_http"])
def test_some_failures_say_nothing_about_the_project(kind: str) -> None:
    # The model's mistake, the user's Ctrl-C, and the provider's bad day.
    assert template(ErrorRecord(tool="shell", kind=kind), 9) is None  # type: ignore[arg-type]


def test_the_same_failure_is_the_same_key() -> None:
    a = ErrorRecord(tool="shell", kind="timeout", program="pytest")
    b = ErrorRecord(tool="shell", kind="timeout", program="pytest", exit_code=1)
    assert key(a) == key(ErrorRecord(tool="shell", kind="timeout", program="pytest"))
    assert key(a) != key(b)


# --- history.md --------------------------------------------------------------


def test_an_entry_has_the_six_lines_and_is_redacted(tmp_path: Path) -> None:
    run = Run(
        session="0f3a1c",
        prompt="deploy with sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF0123",
        tools=["read", "edit", "read"],
        paths=["src/a.py"],
        said=["done"],
        cost=0.0142,
        verification="passed",
    )
    text = entry(run)
    assert "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF0123" not in text
    assert "- did: read, edit\n" in text  # in call order, deduplicated
    assert "- files: src/a.py\n" in text
    assert "- outcome: stop · verification passed" in text
    assert text.splitlines()[0].endswith("· $0.0142")


def test_a_long_prompt_is_condensed_and_says_so() -> None:
    short = "just five words here now"
    assert condense(short) == short
    long = " ".join(f"w{i}" for i in range(500))
    assert condense(long).startswith("w0 w1 ")
    assert "(460 more words; see `edgar stats`)" in condense(long)


def test_the_file_rotates_instead_of_growing(tmp_path: Path) -> None:
    path = tmp_path / ".edgar" / "history.md"
    history = History(path, cap=400)
    run = Run(session="s", prompt="a prompt worth a line", said=["ok"])
    for _ in range(12):
        history.append(run)
    assert path.with_suffix(".1.md").exists()
    assert path.stat().st_size < CAP


def test_distilled_facts_are_pending_and_never_active(tmp_path: Path, memory: Memory) -> None:
    # history.md holds a "- said:" line, which the model wrote, so nothing derived
    # from the file may be active [MEM-17, ADR-0017].
    path = tmp_path / "history.md"
    history = History(path)
    for _ in range(4):
        history.append(Run(session="s", prompt="p", tools=["read", "edit"], paths=["src/a.py"]))
    facts = distill(path, memory, P)
    assert facts
    assert {f.status for f in facts} == {"pending"}
    assert {f.provenance for f in facts} == {"distilled"}
    assert memory.facts([P]) == []
    assert len(entries(path)) == 4


def test_history_is_not_written_when_it_is_turned_off(tmp_path: Path, memory: Memory) -> None:
    bus = EventBus()
    attach(bus, root=tmp_path, session="s", memory=memory, scope=P, history=False)
    bus.emit(PromptTyped(text="do a thing"))
    bus.emit(_turn())
    assert not (tmp_path / ".edgar" / "history.md").exists()
    assert Experience(tmp_path / ".edgar" / "learning.db").stats().runs == 1


def test_autolearn_off_leaves_the_telemetry_on(tmp_path: Path, memory: Memory) -> None:
    bus = EventBus()
    attach(bus, root=tmp_path, session="s", memory=memory, scope=P, autolearn=False)
    bus.emit(PromptTyped(text="remember that we deploy with just ship"))
    bus.emit(_turn())
    assert memory.facts([P]) == []
    assert Experience(tmp_path / ".edgar" / "learning.db").stats().runs == 1


# --- the commands ------------------------------------------------------------


def test_stats_and_history_print_nothing_alarming_when_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["stats"], tmp_path) == 0
    assert command(["history", "show"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "no runs recorded yet" in out and "no history yet" in out


def test_stats_reports_what_the_runs_add_up_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = Experience(tmp_path / ".edgar" / "learning.db")
    store.record(Run(session="s", prompt="p", tools=["read"], cost=0.01, verification="passed"))
    store.record(Run(session="s", prompt="p", tools=["read", "edit"], cost=0.03, failures=1))
    assert command(["stats"], tmp_path) == 0
    out = capsys.readouterr().out
    assert "runs       2 since " + time.strftime("%Y-%m-%d") in out
    assert "verification" not in out  # the word is a heading, not a repeated label
    assert "$0.0400" in out
    assert "read 2, edit 1" in out
    assert "1 runs had a failing tool call" in out


def test_distill_says_the_facts_are_proposals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    history = History(tmp_path / ".edgar" / "history.md")
    for _ in range(4):
        history.append(Run(session="s", prompt="p", tools=["read"], paths=["src/a.py"]))
    assert command(["history", "distill"], tmp_path, home=tmp_path / "home") == 0
    out = capsys.readouterr().out
    assert "none active" in out and "edgar memory review" in out


def test_an_unknown_subcommand_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert command(["history", "rewrite"], tmp_path) == 2
    assert "usage: edgar stats" in capsys.readouterr().err
