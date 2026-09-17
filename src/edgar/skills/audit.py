"""Judge a skill before it is copied in [SKL-18, ADR-0042].

Deterministic checks decide, and nothing else does. A skill is instructions a
future session follows, and the text under review may be hostile: a skill
written to attack the user can hold a prompt injection aimed at whichever model
reads it, including a reviewer. So every verdict here comes from a pattern or a
structural rule, none of it from a model, and the report says in one line that a
clean audit means "no known pattern matched" and never "this skill is safe".
"""

# audit(folder):
#   1. conformance: does it load, is it named after its folder, does the
#      description say when to use it, do its relative paths stay inside, is the
#      body small enough — and, under --strict, has it SKL-16's four sections
#   2. dangers: every line of every text file in the folder against the rule
#      table below, plus every bundled script with the programs it calls
#   3. the report: conformance and dangers kept apart, one finding per rule
#   4. --diff: the deterministic fixes as a unified diff on stdout, never applied
#
# The danger list is data — one row per rule — so a new pattern is a new row and
# a test, never a new branch. ADR-0042's `--review` (an opt-in, advisory model
# read) is not built: it is the only part that costs money and it never changes
# the verdict, so it yields to the budget. The split it protects is kept: if it
# ever lands, it may add findings and must not set the exit code.

from __future__ import annotations

import difflib
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from edgar.context.tokens import approx_tokens
from edgar.skills.discovery import lint, read

MAX_BODY_TOKENS = 5_000
SECTIONS = ("when to use", "procedure", "pitfalls", "verification")  # [SKL-16]
HIDDEN = re.compile(r"[​-‏‪-‮⁦-⁩]")
SCRIPTS = (".sh", ".bash", ".py", ".ps1", ".js", ".rb", ".pl")
TEXT = (".md", ".txt", ".toml", ".json", ".yaml", ".yml", *SCRIPTS)
CALLS = re.compile(r"^\s*(?:\$\s*)?([a-z][\w.-]{1,30})\s", re.M)

# Each row: rule id, what it looks for, and what it means. Order is the report's.
DANGERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("SA-D1", re.compile(r"(curl|wget)[^\n|]*\|\s*(ba|z|fi)?sh"), "a download piped into a shell"),
    ("SA-D2", re.compile(r"\bsudo\b"), "sudo"),
    (
        "SA-D3",
        re.compile(r"\brm\s+-[a-z]*[rR][a-z]*f|\brm\s+-[a-z]*f[a-z]*[rR]"),
        "a recursive delete",
    ),
    ("SA-D4", re.compile(r"\beval\b"), "eval"),
    ("SA-D5", re.compile(r"EDGAR_YOLO|--yolo|\byolo\b"), "an instruction to widen policy"),
    ("SA-D6", re.compile(r"--no-verify|skip the check|don'?t ask|do not ask"), "skipping a check"),
    ("SA-D7", re.compile(r"don'?t tell|do not tell|without telling"), "hiding work from the user"),
    ("SA-D8", HIDDEN, "hidden or bidi characters"),
    ("SA-D9", re.compile(r"<!--"), "an HTML comment: text a reader does not see"),
    ("SA-D10", re.compile(r"[A-Za-z0-9+/]{120,}={0,2}"), "a long base64 run"),
    ("SA-D11", re.compile(r"~/\.ssh|\bid_rsa\b|\.env\b|keychain|keyring"), "a credential location"),
    ("SA-D12", re.compile(r"https?://[\w.-]+"), "a host it names"),
    ("SA-D13", re.compile(r"\.\./"), "a path that leaves the skill's folder"),
)


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    kind: str  # "conformance" or "danger"
    where: str  # file:line, or the folder for a whole-skill rule
    message: str


@dataclass(frozen=True, slots=True)
class Report:
    folder: Path
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.kind == "conformance")

    @property
    def dangers(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.kind == "danger")


def audit(folder: Path, *, strict: bool = False) -> Report:
    # 1. Conformance first: a skill that does not load cannot be read for dangers
    #    in any meaningful way, but the danger scan runs on its text anyway.
    findings = list(_conformance(folder, strict=strict))
    # 2. Dangers, over every text file in the folder, the rule table in order.
    findings += _dangers(folder)
    return Report(folder, tuple(findings))


def _conformance(folder: Path, *, strict: bool) -> list[Finding]:
    here = folder.name
    path = folder / "SKILL.md"
    if not path.is_file():
        return [Finding("SA-1", "conformance", here, "no SKILL.md in this folder")]
    try:
        skill = read(path, "audited")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [Finding("SA-1", "conformance", f"{path}:1", str(exc))]
    found = []
    if warn := lint(skill):  # SKL-17's own rule, not a second copy of it
        found.append(Finding("SA-2", "conformance", str(path), warn))
    body = path.read_text(encoding="utf-8")
    found += _paths_stay_inside(folder, body)
    tokens = approx_tokens(body)
    if tokens > MAX_BODY_TOKENS:
        found.append(
            Finding(
                "SA-4", "conformance", str(path), f"~{tokens:,} tokens, over {MAX_BODY_TOKENS:,}"
            )
        )
    if strict:
        found += _sections(path, body)
    return found


def _paths_stay_inside(folder: Path, body: str) -> list[Finding]:
    # Every relative link in the body has to resolve inside the skill's folder
    # [SKL-5]: a skill's resources are its own, and nobody else's.
    out = []
    for match in re.finditer(r"\]\(([^)#:]+)\)", body):
        target = match[1].strip()
        if target.startswith(("/", "http")):
            continue
        where = (folder / target).resolve()
        if not where.is_relative_to(folder.resolve()):
            out.append(Finding("SA-3", "conformance", str(folder), f"{target} leaves the folder"))
    return out


def _sections(path: Path, body: str) -> list[Finding]:
    lower = body.lower()
    missing = [s for s in SECTIONS if f"# {s}" not in lower]
    if not missing:
        return []
    return [Finding("SA-5", "conformance", str(path), f"--strict: no {', '.join(missing)} section")]


def _dangers(folder: Path) -> list[Finding]:
    out = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        out += _bundled_program(folder, path)
        if path.suffix.lower() not in TEXT:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = path.relative_to(folder).as_posix()
        for number, line in enumerate(lines, 1):
            for rule, pattern, says in DANGERS:
                if pattern.search(line):
                    out.append(
                        Finding(rule, "danger", f"{rel}:{number}", f"{says}: {line.strip()[:70]}")
                    )
    return out


def _bundled_program(folder: Path, path: Path) -> list[Finding]:
    # Every bundled executable or script, with the programs it calls: a skill is
    # instructions, and anything in it that runs is worth naming out loud.
    executable = bool(path.stat().st_mode & stat.S_IXUSR)
    if path.suffix.lower() not in SCRIPTS and not executable:
        return []
    rel = path.relative_to(folder).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [Finding("SA-D14", "danger", rel, "a bundled executable")]
    calls = sorted({m[1] for m in CALLS.finditer(text)})[:12]
    return [Finding("SA-D14", "danger", rel, f"a bundled script; it names {', '.join(calls)}")]


def render(report: Report) -> list[str]:
    """The report, conformance and dangers kept apart [ADR-0042]."""
    lines = [f"{report.folder}"]
    lines += [f"  conformance {f.rule} {f.where}: {f.message}" for f in report.errors] or [
        "  conformance: no rule broken"
    ]
    lines += [f"  danger {f.rule} {f.where}: {f.message}" for f in report.dangers] or [
        "  dangers: no known pattern matched"
    ]
    lines.append("  a clean audit means no known pattern matched, never that a skill is safe")
    return lines


def diff(folder: Path) -> str:
    """The deterministic fixes, as a unified diff for `git apply` or review. It is
    printed and never applied, so the audit writes nothing [PRD §9.5]."""
    path = folder / "SKILL.md"
    if not path.is_file():
        return ""
    before = path.read_text(encoding="utf-8")
    after = HIDDEN.sub("", before)
    missing = [s for s in SECTIONS if f"# {s}" not in after.lower()]
    if missing:
        after = after.rstrip("\n") + "\n" + "".join(f"\n## {s.title()}\n\nTODO\n" for s in missing)
    rel = path.relative_to(folder.parent).as_posix()
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            f"a/{rel}",
            f"b/{rel}",
        )
    )


def command(argv: list[str]) -> int:
    # edgar skills audit PATH [--strict] [--diff]. Exit 1 on a conformance finding,
    # as `skills validate` does; a danger finding is printed and gates `ext add`.
    import sys

    flags = set(argv[1:])
    if not argv or flags - {"--strict", "--diff"}:
        print("usage: edgar skills audit PATH [--strict] [--diff]", file=sys.stderr)
        return 2
    folder = Path(argv[0]).expanduser().resolve()
    report = audit(folder, strict="--strict" in flags)
    print("\n".join(render(report)))
    if "--diff" in flags:
        sys.stdout.write(diff(folder) or "# no deterministic fix to propose\n")
    return 1 if report.errors else 0


def skill_folders(target: Path) -> list[Path]:
    """The skills `ext add` would copy: an extension's `skills/*/`, or the folder
    itself when it is one skill."""
    if (target / "SKILL.md").is_file():
        return [target]
    inside = target / "skills"
    return sorted(p.parent for p in inside.glob("*/SKILL.md")) if inside.is_dir() else []
