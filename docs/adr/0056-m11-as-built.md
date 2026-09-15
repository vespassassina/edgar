# ADR-0056 — M11, docs, examples and release automation as built

**Status:** Accepted · 2026-09-15 · Completes M11 and 1.0; implements NFR-10 in
part, ADR-0001's Secondary and Tertiary tiers

## Context

M11 is the last v1 milestone: `edgar init` and `edgar doctor` [CFG-4, CFG-5] were
built and committed earlier this session (`3228336`), closing v1's LOC budget
back to exactly 8,000/8,000. What was left, all of it free against that budget
since none of it touches `src/edgar/`: `docs/COOKBOOK.md` additions,
`docs/EXTENDING.md` and `docs/DEPENDENCIES.md` (both new), an example extension
under `examples/`, a docs-coverage test [NFR-10], and release automation beyond
PyPI (PyApp binaries and a Docker image, ADR-0001's Secondary and Tertiary
tiers). None of it changes `src/`, so the budget stayed at 8,000/8,000 throughout.

Four decisions were not obvious enough to leave unrecorded.

## Options and decisions

**1. `docs/DEPENDENCIES.md` versus ADR-0019, which lists `rich` as required.**
`rich` is never imported anywhere in `src/`; `cli/render.py`'s own hand-written
renderer replaced it, and `pyproject.toml`'s actual `dependencies` are `httpx`,
`jsonschema`, `prompt-toolkit`, `pyyaml` (4 required) plus the optional `keyring`
extra — 5 of NFR-5's 8 slots, not the 5 required ADR-0019 describes. (A) Treat
this as a bug in the shipped dependency list and add `rich` back. (B) Document
what actually ships and name the mismatch. **Decided: B**, per CLAUDE.md's own
standing instruction to follow what the code does and flag a stale ADR rather
than silently perpetuate or silently "fix" it without the maintainer's say. The
new file cites measured import costs (`python -X importtime`) for all five and
states the mismatch in its own section rather than burying it in a footnote.

**2. The example extension's hook command, and the cross-platform trap in it.**
`examples/extensions/audit-log/hooks.toml` needs a `command` a human can read at
a glance, and `["python", "log_event.py"]` reads better than
`[sys.executable, ...]` baked into the shipped file — but a bare `python` is not
guaranteed on PATH on every CI image. (A) Ship `python3` instead, which is closer
to guaranteed on Linux/macOS but still not universal (Windows more often has
bare `python`). (B) Ship the readable `["python", "log_event.py"]", note the trap
in a comment right above it, and have the one test that actually runs it
substitute `sys.executable` when it copies the extension into a temp project.
**Decided: B** — same fix `tests/e2e/test_startup.py`'s
`test_five_mcp_servers_cost_a_run_nothing` already applies to its own generated
MCP config, so the pattern was already established rather than invented here.
`tests/e2e/test_cli.py::test_j11_the_example_extension_from_the_docs` does the
substitution and separately runs `log_event.py` standalone with a synthetic
event on stdin, which is the part of the hook path a background `asyncio` task's
fire-and-forget timing (EXT-6, EXT-7) makes awkward to assert on end-to-end.

**3. What "every public command and config key documented" [NFR-10] actually
checks.** The two literal words in the requirement leave real room: every CLI
subcommand and REPL slash command, or just the CLI surface; matched against
which docs; config keys as TOML table names or as PRD prose. (A) Enumerate both
CLI and REPL surfaces by hand and check them against every doc in `docs/`,
`docs/PRD.md` included. (B) Read each surface from the code that already
defines it — `edgar.cli.admin.USAGE` for subcommands, the `Config` dataclass's
fields plus its v1 `LATER` keys for config sections — and check only against
the docs a first-week user would actually open (`COOKBOOK.md`, `EXTENDING.md`,
`DEPENDENCIES.md`, `FAQ.md`, `examples/README.md`, plus `templates/config.toml`
and `PRD.md` for config keys specifically), the same way `test_tour.py` reads
the tour's own hooks rather than a hand-maintained list. REPL slash commands are
excluded from the check entirely: `slash.COMMANDS`' `@command(name, help)`
decorator requires a help string by construction, so `/help` is every slash
command's own documentation and a static doc duplicating it would only drift.
**Decided: B.** Running the check against PRD.md alone would have passed
trivially (it is the exhaustive spec); running it found two real gaps —
`edgar doctor`, `edgar permissions` and `edgar logout` had no first-week-doc
mention, and `[prompt]`/`[[route]]` were never once written as literal config
keys anywhere, only described in prose (PRV-17, ROUTE-2). Both were fixed:
COOKBOOK.md gained "Start a new project", "See what a session has done, and
undo it" and "Sign in without an API key" recipes; PRD.md's PRV-17 and ROUTE-2
rows now name the table syntax, not just the behaviour.

**4. Release automation that cannot be run inside this environment.**
ADR-0001's Secondary and Tertiary tiers (PyApp binaries per platform, a Docker
image) need a real GitHub Actions run to prove; this session has no CI runner.
(A) Skip them and leave the gap in the journal. (B) Write them anyway, to the
same pinned-SHA convention as the existing `publish` job, verified as far as
static checks reach (YAML parses, the actions and tags resolved to real commits
via `gh api`), and say plainly that the first real release run is the actual
verification. **Decided: B** — a written, carefully-reasoned workflow that
might have a runtime surprise is worth more than no workflow, provided the gap
is named rather than implied to be tested. Two new jobs ride the existing
`on: release: types: [published]` trigger: `pyapp` (matrix over
ubuntu/macos/windows-latest, `cargo install pyapp` with `PYAPP_PROJECT_VERSION`
taken from the release tag with its leading `v` stripped, uploaded to the
release with `gh release upload`) and `docker` (`docker/build-push-action` to
`ghcr.io/vespassassina/edgar`, tagged with the stripped version and `latest`).
The root `Dockerfile` `pip install`s the exact PyPI release rather than copying
the working tree, so the published image is provably what anyone else's `pip
install edgar-harness` gives them — the same reasoning that lets `pyapp`'s
binaries skip any ordering against `publish`, since each one only `pip
install`s the named PyPI version the first time it runs, never at CI build
time.

## Consequences

M11 and v1.0 are done: `docs/EXTENDING.md` and `docs/DEPENDENCIES.md` (new),
three new Cookbook recipes plus the extensions-and-hooks one, an example
extension exercised by both `tests/e2e/test_cli.py::test_j11_…` and
`tests/unit/test_docs_coverage.py` [NFR-10], and PyApp/Docker jobs alongside the
existing PyPI trusted-publishing job. `src/` is untouched and still exactly
8,000/8,000; every change here is free against the v1 budget by construction
(`count_loc` only globs `src/edgar/**/*.py`).

Against that: the docs-coverage test's regex matching is deliberately loose
(a bare word boundary, not a citation graph), so it catches an undocumented
name but not stale or wrong prose about a documented one — the same limit
`test_tour.py` already accepts for the same reason. The release workflow's two
new jobs are unverified by any real run; the first tagged release is where that
either holds or does not, and any fix from that point is worth its own ADR
entry rather than a silent edit to this one.
