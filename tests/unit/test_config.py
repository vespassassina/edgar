"""Config layering, provenance and error messages [CFG-1, CFG-2, CFG-3]."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar.config.load import load
from edgar.core.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults(tmp_project: Path, home: Path) -> None:
    config = load(tmp_project, home=home, env={})
    assert config.permissions.mode == "ask"
    assert config.tools.max_output_tokens == 8000
    assert config.instructions.files == ["AGENTS.md"]
    assert config.model.default is None
    assert set(config.origins.values()) == {"default"}


def test_layers_override_in_order_and_record_their_origin(tmp_project: Path, home: Path) -> None:
    user = _write(
        home / ".edgar" / "config.toml",
        '[model]\ndefault = "a/user"\n'
        "[tools]\nmax_output_tokens = 1\n"
        "[context]\ncompact_at = 0.6\n",
    )
    project = _write(
        tmp_project / ".edgar" / "config.toml",
        '[model]\ndefault = "b/project"\n[tools]\nmax_output_tokens = 2\n',
    )
    env = {"EDGAR_TOOLS_MAX_OUTPUT_TOKENS": "3"}
    flags = {"model.default": ("c/flag", "flag --model")}
    config = load(tmp_project, home=home, env=env, flags=flags)

    assert config.model.default == "c/flag"
    assert config.tools.max_output_tokens == 3
    assert config.context.compact_at == 0.6
    assert config.origins["model.default"] == "flag --model"
    assert config.origins["tools.max_output_tokens"] == "env EDGAR_TOOLS_MAX_OUTPUT_TOKENS"
    assert config.origins["context.compact_at"] == str(user)
    assert config.origins["verify.max_attempts"] == "default"
    assert str(project) not in config.origins.values()  # every project value was overridden


@pytest.mark.parametrize(
    ("toml", "expected"),
    [
        (
            '[tools]\nmax_output_tokens = "8k"\n',
            "[tools] max_output_tokens must be an integer, got string",
        ),
        ('[permissions]\nmode = "careful"\n', 'must be one of "read-only", "ask", "auto", "yolo"'),
        ("[context]\nautocompact = 1\n", "must be true or false, got integer"),
        ('[instructions]\nfiles = "AGENTS.md"\n', "must be a list of strings, got string"),
        ("[tools]\nmax_output_token = 8\n", "did you mean max_output_tokens?"),
        ("[tool]\nx = 1\n", "unknown section [tool]"),
        ('mode = "ask"\n', "unknown section [mode]"),
        ("[model]\ndefault = \n", "not valid TOML"),
    ],
)
def test_errors_name_the_file_the_key_and_the_expectation(
    tmp_project: Path, home: Path, toml: str, expected: str
) -> None:
    path = _write(tmp_project / ".edgar" / "config.toml", toml)
    with pytest.raises(ConfigError) as info:
        load(tmp_project, home=home, env={})
    assert str(path) in str(info.value)
    assert expected in f"{info.value} {info.value.hint}"
    assert info.value.exit_code == 3


def test_integers_are_accepted_where_numbers_are_expected(tmp_project: Path, home: Path) -> None:
    _write(tmp_project / ".edgar" / "config.toml", "[budget]\nturn_cost_cap = 1\n")
    assert load(tmp_project, home=home, env={}).budget.turn_cost_cap == 1


def test_sections_for_later_milestones_are_kept_not_rejected(tmp_project: Path, home: Path) -> None:
    _write(
        tmp_project / ".edgar" / "config.toml",
        '[[route]]\nname = "x"\n[model.fallback]\n"a/b" = ["c/d"]\n[subagents]\nmax_depth = 2\n'
        '[browser]\ncommand = "npx"\n',
    )
    config = load(tmp_project, home=home, env={})
    assert set(config.later) == {"route", "model.fallback", "subagents"}
    assert config.browser.command == "npx"  # read since M8


def test_mcp_blocks_merge_across_files_and_are_checked(tmp_project: Path, home: Path) -> None:
    _write(home / ".edgar" / "config.toml", '[mcp.gh]\ncommand = "gh-mcp"\nargs = ["-v"]\n')
    _write(tmp_project / ".edgar" / "config.toml", '[mcp.gh]\nenv = { T = "${env:T}" }\n')
    config = load(tmp_project, home=home, env={})
    assert config.mcp["gh"].command == "gh-mcp" and config.mcp["gh"].env == {"T": "${env:T}"}
    assert config.origins["mcp.gh.env"] == str(tmp_project / ".edgar" / "config.toml")
    _write(tmp_project / ".edgar" / "config.toml", "[mcp.gh]\nargs = 3\n")
    with pytest.raises(ConfigError, match=r"\[mcp.gh\] args must be a list"):
        load(tmp_project, home=home, env={})


@pytest.mark.parametrize(
    ("name", "raw", "key", "value"),
    [
        ("EDGAR_CONTEXT_AUTOCOMPACT", "off", "autocompact", False),
        ("EDGAR_CONTEXT_COMPACT_AT", "0.8", "compact_at", 0.8),
        ("EDGAR_INSTRUCTIONS_FILES", "AGENTS.md, CLAUDE.md", "files", ["AGENTS.md", "CLAUDE.md"]),
        ("EDGAR_VERIFY_COMMAND", "", "command", None),
        ("EDGAR_PERMISSIONS_MODE", "auto", "mode", "auto"),
    ],
)
def test_environment_values_are_parsed_by_type(
    tmp_project: Path, home: Path, name: str, raw: str, key: str, value: object
) -> None:
    config = load(tmp_project, home=home, env={name: raw})
    section = name.split("_")[1].lower()
    assert getattr(getattr(config, section), key) == value


def test_bad_environment_values_name_the_variable(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="environment variable EDGAR_TOOLS_MAX_OUTPUT_TOKENS"):
        load(tmp_project, home=home, env={"EDGAR_TOOLS_MAX_OUTPUT_TOKENS": "lots"})
    with pytest.raises(ConfigError, match="EDGAR_TOOLS_MAX_OUTPUT_TOKEN:") as info:
        load(tmp_project, home=home, env={"EDGAR_TOOLS_MAX_OUTPUT_TOKEN": "1"})
    assert info.value.hint == "did you mean EDGAR_TOOLS_MAX_OUTPUT_TOKENS?"


def test_other_programs_edgar_variables_are_left_alone(tmp_project: Path, home: Path) -> None:
    # edgartools, an unrelated SEC library, reads EDGAR_IDENTITY.
    load(tmp_project, home=home, env={"EDGAR_IDENTITY": "someone@example.com"})


def test_bad_flag_values_are_rejected(tmp_project: Path, home: Path) -> None:
    with pytest.raises(ConfigError, match="flag --mode"):
        load(tmp_project, home=home, env={}, flags={"permissions.mode": ("root", "flag --mode")})
