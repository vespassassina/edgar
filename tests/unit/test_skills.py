"""Skills: discovery, the `skill` tool, the index in the prompt, and the CLI [SKL-1..5, SKL-7]."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from harness import Recorder, new_session, runtime, scripted, tool_use
from scripted import ScriptedResponse

from edgar.cli import admin
from edgar.cli.setup import runtime as build_runtime
from edgar.cli.setup import setup
from edgar.config.schema import Config, ModelSection
from edgar.context.tokens import message_text
from edgar.core.events import EventBus
from edgar.core.loop import run_turn
from edgar.core.message import Message, ToolUseBlock
from edgar.skills.activate import activate, touched_paths, verify_command
from edgar.skills.discovery import Skill, discover, split
from edgar.tools.base import ToolContext
from edgar.tools.builtin.skill import SkillTool
from edgar.tools.custom import load

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _skill(scope: Path, name: str, description: str = "Use when testing.", body: str = "") -> Path:
    folder = scope / name
    folder.mkdir(parents=True, exist_ok=True)
    text = f"---\nname: {name}\ndescription: {description}\n---\n{body or f'The {name} body.'}\n"
    (folder / "SKILL.md").write_text(text, encoding="utf-8")
    return folder


def _project(root: Path) -> Path:
    return root / ".edgar" / "skills"


def _user(home: Path) -> Path:
    return home / ".edgar" / "skills"


# discovery [SKL-1, SKL-3]


def test_discovery_reads_the_frontmatter_of_each_scope(tmp_project: Path, home: Path) -> None:
    _skill(_project(tmp_project), "deploy", "Use when deploying.")
    _skill(_user(home), "review", "Use when reviewing\n  a change.")
    found = discover(tmp_project, home)
    assert sorted(found.skills) == ["deploy", "review"]
    assert found.skills["review"].description == "Use when reviewing a change."  # one line
    assert found.skills["deploy"].origin == "project"
    assert found.problems == found.warnings == []


def test_the_project_wins_and_says_so(tmp_project: Path, home: Path) -> None:
    _skill(_user(home), "deploy", "user")
    _skill(_project(tmp_project), "deploy", "project")
    found = discover(tmp_project, home)
    assert found.skills["deploy"].description == "project"
    assert found.warnings == ["the project skill 'deploy' replaces the user one"]


def test_a_learned_skill_never_shadows_a_hand_authored_one(tmp_project: Path, home: Path) -> None:
    _skill(_user(home), "deploy", "written by a human")
    _skill(_project(tmp_project) / "learned", "deploy", "learned")
    _skill(_project(tmp_project) / "learned", "lint", "learned lint")
    found = discover(tmp_project, home)
    assert found.skills["deploy"].description == "written by a human"
    assert found.skills["lint"].origin == "project learned"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("no frontmatter here\n", "no frontmatter"),
        ("---\nname: [unclosed\n---\n", "not YAML"),
        ("---\n- a list\n---\n", "mapping"),
        ("---\nname: Bad_Name\ndescription: x\n---\n", "lowercase"),
        ("---\nname: other\ndescription: x\n---\n", "the folder is 'broken'"),
        ("---\nname: broken\n---\n", "description"),
        ("---\nname: broken\ndescription: !!python/object:os.system x\n---\n", "not YAML"),
    ],
)
def test_a_broken_skill_is_skipped_with_its_reason(
    tmp_project: Path, home: Path, text: str, problem: str
) -> None:
    (_project(tmp_project) / "broken").mkdir(parents=True)
    (_project(tmp_project) / "broken" / "SKILL.md").write_text(text, encoding="utf-8")
    _skill(_project(tmp_project), "fine")
    found = discover(tmp_project, home)
    assert list(found.skills) == ["fine"]
    assert len(found.problems) == 1 and problem in found.problems[0]


def test_frontmatter_with_windows_line_endings_parses() -> None:
    head, body = split("---\r\nname: x\r\ndescription: y\r\n---\r\nbody\r\n")
    assert head == {"name": "x", "description": "y"} and body.strip() == "body"


def test_finding_no_skills_never_imports_yaml(tmp_project: Path, home: Path) -> None:
    code = (
        "import sys; from pathlib import Path; from edgar.skills.discovery import discover; "
        f"discover(Path({str(tmp_project)!r}), Path({str(home)!r})); "
        "sys.exit('yaml' in sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0  # [NFR-1]


# the skill tool and the prompt [SKL-2, SKL-4, SKL-5]


def _ctx(root: Path) -> ToolContext:
    return ToolContext(cwd=root, bus=EventBus(), blob_dir=root / "blobs", max_output_tokens=8000)


def test_the_tool_returns_the_body_and_where_it_lives(tmp_project: Path, home: Path) -> None:
    folder = _skill(_project(tmp_project), "deploy", body="Run ./deploy.sh from this folder.")
    tool = SkillTool(discover(tmp_project, home).skills)
    result = asyncio.run(tool.run({"name": "deploy"}, _ctx(tmp_project)))
    assert result.error is None
    assert "Run ./deploy.sh" in result.text and str(folder) in result.text
    assert "description:" not in result.text  # the frontmatter is not repeated
    assert tool.schema.input_schema["properties"]["name"]["enum"] == ["deploy"]
    missing = asyncio.run(tool.run({"name": "nope"}, _ctx(tmp_project)))
    assert missing.error == "not_found" and "deploy" in missing.text


def test_the_prompt_holds_the_index_and_never_a_body(tmp_project: Path, home: Path) -> None:
    config = Config(model=ModelSection(default="fake/test"))
    assert "skill" not in setup(tmp_project, config, home=home, env={}).tools.names()
    _skill(_project(tmp_project), "deploy", "Use when deploying.", body="SECRET STEPS")
    s = setup(tmp_project, config, home=home, env={})
    prompt = build_runtime(s, EventBus()).system_prompt
    assert "- deploy: Use when deploying." in prompt and "SECRET STEPS" not in prompt
    assert "skill" in s.tools.names()


def test_a_broken_skill_is_a_startup_warning(tmp_project: Path, home: Path) -> None:
    (_project(tmp_project) / "bad").mkdir(parents=True)
    (_project(tmp_project) / "bad" / "SKILL.md").write_text("nothing", encoding="utf-8")
    s = setup(tmp_project, Config(model=ModelSection(default="fake/test")), home=home, env={})
    assert any("bad" in w and "no frontmatter" in w for w in s.warnings)


def test_the_model_loads_a_skill_in_a_turn(tmp_project: Path, home: Path) -> None:
    _skill(_project(tmp_project), "deploy", body="Step one: breathe.")
    config = Config(model=ModelSection(default="fake/test"))
    tools = setup(tmp_project, config, home=home, env={}).tools
    provider = scripted(
        ScriptedResponse(tool_calls=[tool_use("skill", {"name": "deploy"})]),
        ScriptedResponse(text="done"),
    )
    rec = Recorder()
    session = new_session(tmp_project)
    asyncio.run(run_turn(session, "deploy it", runtime(provider, rec, tools=tools)))
    (result,) = [m for m in session.transcript if m.role == "tool"]
    assert "Step one: breathe." in message_text(result)
    assert "ToolFinished" in rec.names


# the CLI [SKL-7, TOOL-9]


def test_skills_list_and_validate(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.command(["skills", "list"], tmp_project, home) == 0
    assert "no skills" in capsys.readouterr().out
    _skill(_project(tmp_project), "deploy", "Use when deploying.")
    assert admin.command(["skills", "list"], tmp_project, home) == 0
    assert "deploy" in capsys.readouterr().out
    assert admin.command(["skills", "validate"], tmp_project, home) == 0
    (_project(tmp_project) / "bad").mkdir()
    (_project(tmp_project) / "bad" / "SKILL.md").write_text("x", encoding="utf-8")
    assert admin.command(["skills", "validate"], tmp_project, home) == 1
    out = capsys.readouterr()
    assert "1 skills ok, 1 with problems" in out.out and "no frontmatter" in out.err
    assert admin.command(["skills", "frob"], tmp_project, home) == 2


def test_tools_list_and_describe(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(_project(tmp_project), "deploy")
    assert admin.command(["tools", "list"], tmp_project, home) == 0
    listed = capsys.readouterr().out
    assert "read " in listed and "skill " in listed and "builtin" in listed
    assert admin.command(["tools", "describe", "read"], tmp_project, home) == 0
    assert '"name": "read"' in capsys.readouterr().out
    assert admin.command(["tools", "describe", "nope"], tmp_project, home) == 2


def test_tools_list_leaves_out_an_untrusted_projects_tools(
    tmp_project: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (_project(tmp_project).parent / "tools").mkdir(parents=True)
    shutil.copy(EXAMPLES / "tools" / "gh_issue.toml", tmp_project / ".edgar" / "tools")
    assert admin.command(["tools", "list"], tmp_project, home) == 0
    assert "gh_issue" not in capsys.readouterr().out  # [PERM-13]
    assert admin.command(["trust", "--yes"], tmp_project, home) == 0
    capsys.readouterr()
    assert admin.command(["tools", "list"], tmp_project, home) == 0
    assert "gh_issue" in capsys.readouterr().out


# the examples work as they are


def test_the_example_tools_load() -> None:
    tools = load([(EXAMPLES / "tools", "project")])
    assert sorted(t.schema.name for t in tools) == [
        "dropbox_ls",
        "gcal_events",
        "gdocs_get",
        "gh_issue",
        "gmail_search",
        "onedrive_ls",
        "service_status",
        "weather",
        "web_search",
    ]
    for path in (EXAMPLES / "tools").glob("*.toml"):
        tomllib.loads(path.read_text(encoding="utf-8"))


def test_the_example_skills_validate(tmp_project: Path, home: Path) -> None:
    shutil.copytree(EXAMPLES / "skills", _project(tmp_project))
    found = discover(tmp_project, home)
    assert found.problems == [] and "changelog" in found.skills
    assert (found.skills["changelog"].path.parent / "template.md").is_file()  # [SKL-5]


# deterministic activation [SKL-17]


def test_a_typed_keyword_activates_a_skill(tmp_project: Path) -> None:
    folder = _skill(_project(tmp_project), "deploy", body="Run `just ship`.")
    skill = Skill("deploy", "Use when deploying.", folder / "SKILL.md", "project", (), ("ship",))
    hits = activate({"deploy": skill}, "please ship this", ())
    assert hits == ["skill deploy:\nRun `just ship`."]
    assert activate({"deploy": skill}, "please build this", ()) == []


def test_a_touched_path_activates_a_skill(tmp_project: Path) -> None:
    folder = _skill(_project(tmp_project), "migrate", body="Check the schema.")
    skill = Skill("migrate", "Use when migrating.", folder / "SKILL.md", "project", ("*.sql",))
    hits = activate({"migrate": skill}, "hi", ("schema.sql",))
    assert hits == ["skill migrate:\nCheck the schema."]
    assert activate({"migrate": skill}, "hi", ("readme.md",)) == []


def test_touched_paths_reads_the_most_recent_round_of_tool_calls() -> None:
    calls = (ToolUseBlock("1", "read", {"path": "a.txt"}), ToolUseBlock("2", "write", {}))
    transcript = [Message.user("hi"), Message(role="assistant", content=calls)]
    assert touched_paths(transcript) == ("a.txt",)
    assert touched_paths([]) == ()
    assert touched_paths([Message.user("hi")]) == ()


def test_verify_command_chains_loaded_skills_in_order(tmp_project: Path) -> None:
    folder = _skill(_project(tmp_project), "a")
    first = Skill("a", "Use when a.", folder / "SKILL.md", "project", verify="one")
    second = Skill("b", "Use when b.", folder / "SKILL.md", "project", verify="two")
    assert verify_command([first, second]) == "one && two"
    assert verify_command([Skill("c", "Use when c.", folder / "SKILL.md", "project")]) is None
    assert verify_command([]) is None
