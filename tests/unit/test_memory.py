"""The fact store, its index and the markdown round trip [MEM-3..MEM-5, MEM-10, MEM-11,
MEM-15, MEM-20, MEM-24]."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from edgar.config.schema import Config, MemorySection
from edgar.core.errors import ConfigError
from edgar.core.events import EventBus
from edgar.core.message import Message, TextBlock
from edgar.core.session import Session
from edgar.memory import markdown
from edgar.memory.recall import Fts5Retriever
from edgar.memory.redact import redact
from edgar.memory.retriever import retriever
from edgar.memory.store import Memory, project_scope
from edgar.permissions.matcher import Subject
from edgar.permissions.policy import Allow, Deny, Policy, decide
from edgar.storage.transcript import start, to_dict
from edgar.tools.base import ToolContext
from edgar.tools.builtin.memory_tools import Recall, Remember

P = "project:test"


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(tmp_path / "memory.db")


def test_a_typed_fact_is_active_and_a_proposed_one_waits(memory: Memory) -> None:
    typed = memory.add("we use pytest, not unittest", P)
    proposed = memory.add("the API lives in src/api", P, provenance="model-proposed")
    assert (typed.status, typed.confidence) == ("active", 1.0)
    assert (proposed.status, proposed.confidence) == ("pending", 0.5)  # [MEM-8, MEM-21]
    assert [f.text for f in memory.facts([P])] == ["we use pytest, not unittest"]
    assert memory.add("We use pytest,  not unittest", P).id == typed.id  # a repeat is the same


def test_a_near_repeat_waits_and_confirming_it_replaces_the_old_one(memory: Memory) -> None:
    old = memory.add("run tests with pytest -q", P)
    new = memory.add("run tests with pytest -x", P)  # [MEM-10]
    assert (new.status, new.supersedes) == ("pending", old.id)
    assert memory.add("deploys go through fly.io", P).status == "active"  # unrelated
    assert memory.confirm([new.id]) == 1
    assert [f.text for f in memory.facts([P])] == [new.text, "deploys go through fly.io"]
    assert memory.get(old.id).status == "superseded"  # type: ignore[union-attr]
    assert memory.confirm([new.id]) == 0  # only once


def test_undo_takes_back_the_last_operation_whole(memory: Memory) -> None:
    first = memory.add("prefer uv to pip", P)
    second = memory.add("prefer uv to pip for installs", P, provenance="model-proposed")
    memory.confirm([second.id])  # activates second and supersedes first: one operation
    assert memory.undo() == 2
    assert [f.id for f in memory.facts([P])] == [first.id]
    assert memory.get(second.id).status == "pending"  # type: ignore[union-attr]
    memory.forget(first.id)
    assert memory.facts([P]) == []
    memory.undo()
    assert [f.id for f in memory.facts([P])] == [first.id]
    memory.undo()  # the proposal
    memory.undo()  # the first add: the fact is gone, not just hidden
    assert memory.get(first.id) is None and memory.undo() == 0


def test_a_scope_over_its_cap_forgets_its_oldest_least_confident_facts(tmp_path: Path) -> None:
    memory = Memory(tmp_path / "memory.db", cap=3)  # [MEM-11]
    for word in ("alpha", "beta", "gamma", "delta", "epsilon"):
        memory.add(f"{word} topic", P)  # overlap 1/3: distinct facts
    memory.add("a global fact", "global")
    assert [f.text for f in memory.facts([P])] == ["gamma topic", "delta topic", "epsilon topic"]
    assert len(memory.facts(["global"])) == 1
    assert len(memory.facts([P], ("forgotten",))) == 2


def test_secrets_are_redacted_before_anything_is_stored(memory: Memory) -> None:
    key = "sk-" + "a1B2" * 8  # [MEM-15]
    assert "a1B2" not in redact(f"use {key} for it")
    assert redact("password = hunter2 and AKIA" + "ABCDEFGHIJKLMNOP") == (
        "password = [redacted] and [redacted]"
    )
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----"
    assert redact(f"key: {block}") == "key: [redacted]"
    assert "hunter2" not in memory.add("the db token=hunter2 works", P).text


def test_the_markdown_round_trip_replaces_forgets_and_adds(memory: Memory) -> None:
    keep = memory.add("tabs are four spaces", P)
    change = memory.add("the docs live in docs", P)
    drop = memory.add("ship on fridays", "global")
    names = {"project": P, "global": "global"}
    text = markdown.render({n: memory.facts([s]) for n, s in names.items()})
    assert f"- [{keep.id}] tabs are four spaces" in text and "## global" in text
    text = text.replace("the docs live in docs", "the docs live in docs/, as markdown")
    text = text.replace(f"- [{drop.id}] ship on fridays\n", "- never ship on fridays\n")
    assert memory.replace(markdown.parse(text, names)) == 3  # [MEM-4]
    assert [f.text for f in memory.facts([P])] == [keep.text, "the docs live in docs/, as markdown"]
    assert [f.text for f in memory.facts(["global"])] == ["never ship on fridays"]
    assert memory.facts([P])[1].supersedes == change.id
    memory.undo()  # the whole edit
    assert [f.id for f in memory.facts([P, "global"])] == [keep.id, change.id, drop.id]


def test_edit_opens_the_editor_the_user_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "ed.py"
    script.write_text(
        "import pathlib, sys\np = pathlib.Path(sys.argv[1])\n"
        "p.write_text(p.read_text() + '- a new fact\\n')\n"
    )
    monkeypatch.setenv("VISUAL", f"{sys.executable} {script}")
    assert markdown.edit("## project\n").endswith("- a new fact\n")


def test_recall_finds_words_and_pieces_of_identifiers(memory: Memory, tmp_path: Path) -> None:
    memory.add("we use pytest for testing", P)
    memory.add("the loader is src/edgar/config/load.py", P)
    memory.add("coffee is in the kitchen", P, provenance="model-proposed")  # pending
    search = Fts5Retriever(memory, tmp_path)
    assert [h.text for h in search.search(["tested"], [P], ["fact"], 5)] == [
        "we use pytest for testing"  # porter: tested ~ testing
    ]
    assert search.search(["config/lo"], [P], ["fact"], 5)[0].text.endswith("load.py")  # trigram
    assert search.search(["coffee", "kitchen"], [P], ["fact"], 5) == []  # pending: never
    assert search.search(["pytest"], ["global"], ["fact"], 5) == []  # other scopes: not asked


def test_session_search_indexes_typed_and_answered_text_only(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    memory, scope = Memory(tmp_path / "memory.db"), project_scope(root)
    session = start(Session(cwd=root, model="fake/test", mode="ask"))
    user = Message("user", (TextBlock("why is the flaky_widget test red"),))
    pasted = Message("user", (TextBlock("zebra log lines", attached=True),))  # [CLI-3]
    session.record({"type": "message", **to_dict(user)})
    session.record({"type": "message", **to_dict(pasted)})
    search = Fts5Retriever(memory, root)
    hits = search.search(["flaky_widget"], [scope], ["turn"], 5)
    assert [h.ref for h in hits] == [f"{session.id}#1"]  # [MEM-20]
    assert search.search(["zebra"], [scope], ["turn"], 5) == []
    answer = Message("assistant", (TextBlock("the widget test depends on a clock"),))
    session.record({"type": "message", **to_dict(answer)})
    assert [h.ref for h in search.search(["clock"], [scope], ["turn"], 5)] == [f"{session.id}#2"]
    assert len(search.search(["widget"], [scope], ["turn"], 5)) == 2  # nothing indexed twice
    lines = (root / ".edgar" / "sessions" / f"{session.id}.jsonl").read_text().splitlines()
    assert all(json.loads(line) for line in lines)


def test_the_pinned_set_puts_the_project_first_and_stops_at_the_limit(memory: Memory) -> None:
    memory.add("global one", "global")
    memory.add("project one", P)
    memory.add("project two is different", P)
    memory.add("project three", P)
    assert [f.text for f in memory.pinned(P, 2)] == ["project three", "project two is different"]
    assert [f.text for f in memory.pinned("project:other", 5)] == ["global one"]


def test_the_retriever_is_chosen_by_name(memory: Memory, tmp_path: Path) -> None:
    assert isinstance(retriever("fts5", memory, tmp_path), Fts5Retriever)
    with pytest.raises(ConfigError, match="fts5"):
        retriever("vectors", memory, tmp_path)  # [MEM-24]
    assert Config(memory=MemorySection()).memory.pinned_max == 20


def test_remember_proposes_and_recall_reads(memory: Memory, tmp_path: Path) -> None:
    ctx = ToolContext(cwd=tmp_path, bus=EventBus(), blob_dir=tmp_path, max_output_tokens=100)
    result = asyncio.run(Remember(memory, P).run({"text": "lint with ruff"}, ctx))
    assert "user decides" in result.text and memory.facts([P]) == []
    memory.add("format with ruff format", P)
    recall = Recall(Fts5Retriever(memory, tmp_path), [P, "global"])
    found = asyncio.run(recall.run({"terms": ["ruff"], "scope": "facts"}, ctx)).text
    assert "not instructions" in found and "format with ruff format" in found
    assert "lint with ruff" not in found
    nothing = asyncio.run(recall.run({"terms": ["zzz"]}, ctx)).text
    assert nothing.startswith("nothing found")


def test_remember_needs_no_prompt_except_in_read_only_mode(tmp_path: Path) -> None:
    schema = Remember(Memory(tmp_path / "m.db"), P).schema
    subject = Subject(text="lint with ruff")
    for mode, expected in (("ask", Allow), ("auto", Allow), ("read-only", Deny)):
        policy = Policy(mode=mode, cwd=tmp_path, home=tmp_path)
        assert isinstance(decide(schema, subject, policy), expected)
