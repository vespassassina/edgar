"""The synthesis triggers, the outline and the learned write [SKL-8, SKL-9, SKL-11, SKL-16].

Three things are under test here, and they are separable on purpose:

1. `triggers()` is arithmetic over one finished turn, like `controller/triggers.py`.
   No model, no clock, no provider: hand it a Turn and it answers.
2. `Outline` is what the synthesiser is allowed to read. The test that matters is
   the negative one — what is *not* in it, whatever the turn did.
3. `write_learned()` is the only path to a skill file, and it refuses more often
   than it writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edgar.config.schema import SkillsSection
from edgar.core.message import ErrorRecord
from edgar.learning.experience import Experience, Run, shape_of
from edgar.learning.synthesis import Outline, Turn, triggers, write_learned
from edgar.skills.discovery import discover

GOOD = "\n".join(
    [
        "## When to use",
        "When a dependency pin changes and the tests have to follow.",
        "## Procedure",
        "1. edit the pin\n2. run the check",
        "## Pitfalls",
        "The lockfile has to be regenerated.",
        "## Verification",
        "`just check` exits 0.",
    ]
)


def _db(tmp_path: Path) -> Experience:
    return Experience(tmp_path / "learning.db")


def _turn(**kw: object) -> Turn:
    base: dict[str, object] = {"prompt": "bump the pin", "verification": "passed"}
    return Turn(**{**base, **kw})  # type: ignore[arg-type]


# 1. The four triggers [SKL-8]


def test_a_long_verified_run_trips_trigger_a(tmp_path: Path) -> None:
    turn = _turn(tools=("read", "edit", "shell", "read", "shell", "edit"))
    assert "long" in triggers(turn, SkillsSection(), _db(tmp_path))


def test_a_short_verified_run_trips_nothing(tmp_path: Path) -> None:
    assert triggers(_turn(tools=("read",)), SkillsSection(), _db(tmp_path)) == ()


def test_a_verified_run_that_recovered_from_an_error_trips_trigger_b(tmp_path: Path) -> None:
    turn = _turn(tools=("shell", "shell"), errors=(ErrorRecord("shell", "nonzero_exit"),))
    assert "recovered" in triggers(turn, SkillsSection(), _db(tmp_path))


def test_a_failing_check_trips_nothing_however_long_the_run(tmp_path: Path) -> None:
    # J8's first acceptance line: a turn that ends with a failing check produces no
    # skill. Both of the verified triggers are off, and so is the repeat trigger.
    turn = _turn(verification="failed", tools=("a", "b", "c", "d", "e", "f"))
    assert triggers(turn, SkillsSection(), _db(tmp_path)) == ()


def test_an_unverified_run_trips_nothing(tmp_path: Path) -> None:
    turn = _turn(verification="unverified", tools=("a", "b", "c", "d", "e", "f"))
    assert triggers(turn, SkillsSection(), _db(tmp_path)) == ()


def test_a_correction_trips_trigger_c_even_unverified(tmp_path: Path) -> None:
    # A human correcting the turn is a signal about the *procedure*, not about
    # whether it worked, so it does not wait for a check [SKL-8c].
    turn = _turn(verification="unverified", corrections=("no, use uv",))
    assert triggers(turn, SkillsSection(), _db(tmp_path)) == ("correction",)


def test_the_same_shape_across_sessions_trips_trigger_d(tmp_path: Path) -> None:
    store = _db(tmp_path)
    for n in range(3):
        store.record(Run(session=f"s{n}", prompt="again", tools=["read", "edit"]))
    turn = _turn(tools=("read", "edit"))
    assert "repeated" in triggers(turn, SkillsSection(), store)


def test_a_shape_already_covered_by_a_loaded_skill_does_not_repeat(tmp_path: Path) -> None:
    store = _db(tmp_path)
    for n in range(5):
        store.record(Run(session=f"s{n}", prompt="again", tools=["read", "edit"]))
    turn = _turn(tools=("read", "edit"), skills=("dependency-bump",))
    assert "repeated" not in triggers(turn, SkillsSection(), store)


# OQ-6: what "the same task shape" means


def test_the_shape_is_the_agent_and_the_tools_in_first_seen_order() -> None:
    assert shape_of("", ["read", "edit", "read"]) == "main:read>edit"
    assert shape_of("reviewer", ["edit", "read"]) == "reviewer:edit>read"
    # Order is part of it: editing then reading is not reading then editing.
    assert shape_of("", ["read", "edit"]) != shape_of("", ["edit", "read"])
    assert shape_of("", []) == "main:answer"


# 2. What the synthesiser may read [SKL-9]


def test_the_outline_carries_names_and_counts_and_no_bodies() -> None:
    turn = _turn(
        tools=("shell", "read"),
        errors=(ErrorRecord("shell", "nonzero_exit", exit_code=1, program="pytest"),),
    )
    text = Outline.of(turn, ("long",)).render()
    assert "bump the pin" in text  # the typed prompt: the one safe road
    assert "shell, read" in text
    assert "nonzero_exit" in text
    assert "pytest" in text  # argv[0], scrubbed by the harness before it got here
    assert "passed" in text


def test_the_outline_has_no_place_to_put_tool_output() -> None:
    # Structural, not a filter: Turn has no field for a tool result, so there is
    # nothing for render() to leak. This is the shape M12 asked M14 to copy.
    assert set(Turn.__dataclass_fields__) == {
        "prompt",
        "corrections",
        "tools",
        "errors",
        "verification",
        "agent",
        "skills",
    }


# 3. Writing one [SKL-11, SKL-12, SKL-16]


def test_a_learned_skill_is_written_with_its_provenance(tmp_path: Path) -> None:
    written = write_learned(
        tmp_path, tmp_path, "dependency-bump", GOOD, session="s1", trigger="long"
    )
    assert isinstance(written, Path)
    text = written.read_text(encoding="utf-8")
    assert written.relative_to(tmp_path).as_posix() == (
        ".edgar/skills/learned/dependency-bump/SKILL.md"
    )
    assert "learned: true" in text
    assert "session: s1" in text
    assert "trigger: long" in text


def test_a_learned_skill_that_is_written_can_be_discovered_and_reads_as_learned(
    tmp_path: Path,
) -> None:
    from edgar.skills.discovery import discover

    write_learned(tmp_path, tmp_path, "dependency-bump", GOOD, session="s1", trigger="long")
    found = discover(tmp_path, tmp_path / "home")
    assert found.skills["dependency-bump"].origin == "project learned"
    assert not found.problems


def test_a_body_without_the_four_sections_is_refused(tmp_path: Path) -> None:
    refused = write_learned(tmp_path, tmp_path, "x", "just some prose", session="s", trigger="long")
    assert isinstance(refused, str)
    assert "When to use" in refused
    assert not (tmp_path / ".edgar" / "skills" / "learned").exists()


def test_a_hand_authored_skill_of_the_same_name_is_never_overwritten(tmp_path: Path) -> None:
    hand = tmp_path / ".edgar" / "skills" / "dependency-bump" / "SKILL.md"
    hand.parent.mkdir(parents=True)
    original = "---\nname: dependency-bump\ndescription: use when a pin moves\n---\n\nmine\n"
    hand.write_text(original, encoding="utf-8")
    refused = write_learned(
        tmp_path, tmp_path, "dependency-bump", GOOD, session="s", trigger="long"
    )
    assert isinstance(refused, str)
    assert "hand-authored" in refused
    assert hand.read_text(encoding="utf-8") == original


# --- observations, and the CLI a person uses on them [SKL-6, SKL-12..14, SKL-16] ---


def _learned_skill(root: Path, name: str = "dependency-bump") -> Path:
    written = write_learned(root, root, name, GOOD, session="s1", trigger="long")
    assert isinstance(written, Path)
    return written


def test_a_turn_that_went_well_leaves_no_observation(tmp_path: Path) -> None:
    from edgar.learning.observations import notes, observe

    seen = observe(tmp_path, "dependency-bump", errors=(), corrections=(), verification="passed")
    assert seen == 0 and notes(tmp_path, "dependency-bump") == ()


def test_an_observation_carries_computed_fields_and_typed_lines_only(tmp_path: Path) -> None:
    from edgar.core.message import ErrorRecord
    from edgar.learning.observations import notes, observe

    record = ErrorRecord(tool="shell", kind="nonzero_exit", exit_code=1, program="pytest")
    seen = observe(
        tmp_path,
        "dependency-bump",
        errors=(record,),
        corrections=("no, pin the minor",),
        verification="failed",
    )
    assert seen == 1
    line = notes(tmp_path, "dependency-bump")[0]
    assert "the declared check failed" in line
    assert "shell nonzero_exit" in line and "pytest" not in line  # kinds, not programs
    assert "no, pin the minor" in line
    # Machine-owned, and never beside a file a person wrote [PRD §9.5].
    assert (tmp_path / ".edgar" / "skills" / "learned" / ".history").is_dir()


def test_the_distill_outline_is_the_body_and_the_lines_and_nothing_else(tmp_path: Path) -> None:
    from edgar.learning.observations import outline

    asked = outline("dependency-bump", GOOD, ("the declared check failed",))
    assert asked.startswith("skill: dependency-bump")
    assert "## Procedure" in asked and "the declared check failed" in asked


def test_skills_list_marks_the_learned_ones_and_can_show_only_those(
    tmp_path: Path, capsys: Any
) -> None:
    from edgar.cli import admin

    _learned_skill(tmp_path)
    hand = tmp_path / ".edgar" / "skills" / "handy" / "SKILL.md"
    hand.parent.mkdir(parents=True)
    hand.write_text("---\nname: handy\ndescription: use when tidying\n---\n\nmine\n", "utf-8")
    assert admin.command(["skills", "list"], tmp_path, tmp_path / "home") == 0
    both = capsys.readouterr().out
    assert "dependency-bump" in both and "[learned]" in both and "handy" in both
    assert admin.command(["skills", "list", "--learned"], tmp_path, tmp_path / "home") == 0
    only = capsys.readouterr().out
    assert "dependency-bump" in only and "handy" not in only


def test_skills_forget_archives_a_learned_skill_and_refuses_a_hand_authored_one(
    tmp_path: Path, capsys: Any
) -> None:
    from edgar.cli import admin

    _learned_skill(tmp_path)
    hand = tmp_path / ".edgar" / "skills" / "handy" / "SKILL.md"
    hand.parent.mkdir(parents=True)
    hand.write_text("---\nname: handy\ndescription: use when tidying\n---\n\nmine\n", "utf-8")
    assert admin.command(["skills", "forget", "handy"], tmp_path, tmp_path / "home") == 1
    assert hand.is_file()  # a skill a person wrote is theirs [SKL-12]
    assert admin.command(["skills", "forget", "dependency-bump"], tmp_path, tmp_path / "home") == 0
    assert "archived" in capsys.readouterr().out
    archived = tmp_path / ".edgar" / "skills" / "learned" / ".archive" / "dependency-bump"
    assert (archived / "SKILL.md").is_file()  # archived, never deleted
    assert "dependency-bump" not in discover(tmp_path, tmp_path / "home").skills


def test_skills_validate_fails_on_a_learned_skill_of_the_wrong_shape(tmp_path: Path) -> None:
    from edgar.cli import admin

    written = _learned_skill(tmp_path)
    assert admin.command(["skills", "validate"], tmp_path, tmp_path / "home") == 0
    # Break the shape by hand, the way a bad patch would [SKL-16].
    written.write_text(
        written.read_text(encoding="utf-8").replace("## Pitfalls", "## Gotchas"), encoding="utf-8"
    )
    assert admin.command(["skills", "validate"], tmp_path, tmp_path / "home") == 1


def test_the_auto_disclaimer_says_what_auto_costs(tmp_path: Path) -> None:
    from edgar.cli.setup import AUTO_SYNTHESIS

    # SKL-13's exact promises: what edgar does, that it is unreviewed, how to look.
    assert "without your review" in AUTO_SYNTHESIS
    assert "edgar skills list --learned" in AUTO_SYNTHESIS
