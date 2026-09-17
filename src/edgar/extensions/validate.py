"""`edgar ext validate PATH` and `edgar ext add PATH` [EXT-3].

`validate` reads a bundle with the same loaders a session uses and lists what it
would reject. `add` copies it into `.edgar/extensions/NAME` only after validate
and the skill audit have both passed and a human has said yes: nothing here
widens what a session may do, and nothing is installed unasked [PERM-11].
"""

# ext validate PATH:
#   manifest, then tools/, skills/, agents/ and hooks.toml, each through the
#   module a session loads it with, so a pass here means a session can load it
#
# ext add PATH [--yes]:
#   1. validate: any problem and it refuses, having written nothing
#   2. audit every skill it would copy [SKL-18, ADR-0042], and print the report
#   3. ask. Clean audit: [Y/n]. Any danger finding: [y/N]. No terminal: refuse a
#      danger finding unless --yes was given, so nothing lands unattended
#   4. copy into a sibling temp folder, then one rename into place
#
# Step 4 is what makes a partial copy impossible: the rename is atomic on every
# platform when the destination does not exist, so a session either sees the
# whole extension or none of it. An interrupted copy leaves the temp folder,
# which is removed on the way out and is never on the discovery path anyway.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from edgar.agents.discovery import Found as AgentsFound
from edgar.agents.discovery import scan as scan_agents
from edgar.core.errors import ConfigError
from edgar.extensions.hooks import from_extension
from edgar.extensions.manifest import Manifest, read
from edgar.skills.audit import Report, audit, render, skill_folders
from edgar.skills.discovery import Found as SkillsFound
from edgar.skills.discovery import scan as scan_skills
from edgar.tools.custom import load as load_custom


def validate(folder: Path) -> tuple[Manifest | None, list[str]]:
    """The manifest, and every problem a session would hit loading this bundle."""
    if not folder.is_dir():
        return None, [f"{folder}: no such folder"]
    try:
        manifest = read(folder)
    except ValueError as exc:
        return None, [f"{folder / 'extension.toml'}: {exc}"]
    problems: list[str] = []
    try:
        load_custom([(folder / "tools", "validated")])
    except ConfigError as exc:
        problems.append(str(exc))
    skills, agents = SkillsFound(), AgentsFound()
    scan_skills(folder / "skills", "validated", skills)
    scan_agents(folder / "agents", "validated", agents)
    problems += skills.problems + agents.problems
    try:
        from_extension(folder)
    except ConfigError as exc:
        problems.append(str(exc))
    return manifest, problems


def command(argv: list[str], cwd: Path) -> int:
    if len(argv) < 2 or argv[0] not in ("validate", "add") or set(argv[2:]) - {"--yes"}:
        print("usage: edgar ext validate PATH | edgar ext add PATH [--yes]", file=sys.stderr)
        return 2
    folder = Path(argv[1]).expanduser().resolve()
    manifest, problems = validate(folder)
    for problem in problems:
        print(problem, file=sys.stderr)
    if manifest is None:
        return 1
    counts = _counts(folder)
    print(f"{manifest.name} {manifest.version} · {counts} · {len(problems)} problems")
    if argv[0] == "validate":
        return 1 if problems else 0
    return _add(folder, manifest, problems, cwd, yes="--yes" in argv)


def _counts(folder: Path) -> str:
    kinds = [("tools", "*.toml"), ("skills", "*/SKILL.md"), ("agents", "*.md")]
    parts = [
        f"{len(list((folder / k).glob(g))) if (folder / k).is_dir() else 0} {k}" for k, g in kinds
    ]
    return ", ".join(parts)


def _add(folder: Path, manifest: Manifest, problems: list[str], cwd: Path, *, yes: bool) -> int:
    # 1. A bundle that does not load is never copied, whatever the flags say.
    if problems:
        print(f"refusing to add {manifest.name}: fix the problems above first", file=sys.stderr)
        return 1
    # 2. Every skill it would copy, audited and shown before anything is written.
    reports = [audit(skill) for skill in skill_folders(folder)]
    for report in reports:
        print("\n".join(render(report)))
    if any(r.errors for r in reports):
        print(
            f"refusing to add {manifest.name}: a skill breaks a conformance rule", file=sys.stderr
        )
        return 1
    # 3. Ask, with the default the audit earns [ADR-0042].
    if not _agreed(manifest, reports, yes=yes):
        return 1
    # 4. Copy beside the destination, then one rename.
    dest = cwd / ".edgar" / "extensions" / manifest.name
    if dest.exists():
        print(f"{dest} already exists; remove it first", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    staged = dest.with_name(f".{manifest.name}.incoming")
    shutil.rmtree(staged, ignore_errors=True)
    try:
        shutil.copytree(folder, staged)
        staged.rename(dest)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    print(f"added {manifest.name} to {dest}")
    return 0


def _agreed(manifest: Manifest, reports: list[Report], *, yes: bool) -> bool:
    dangerous = any(r.dangers for r in reports)
    if yes:
        return True
    if not sys.stdin.isatty():
        # Unattended: a clean audit still installs, a danger finding never does.
        if dangerous:
            print("refusing: danger findings and no terminal to ask; pass --yes", file=sys.stderr)
            return False
        return True
    question = f"add {manifest.name}? " + ("[y/N] " if dangerous else "[Y/n] ")
    answer = input(question).strip().lower()
    return answer.startswith("y") or (answer == "" and not dangerous)
