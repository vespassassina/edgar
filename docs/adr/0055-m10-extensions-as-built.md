# ADR-0055 — M10, extensions, hooks, plugins and embedding as built

**Status:** Accepted · 2026-09-15 · Completes M10; refines ADR-0006, ADR-0041;
implements EXT-9, SKL-17, VER-1 in part, CLI-14

## Context

M10's scope, after ADR-0053's second trim, is extension discovery and `edgar ext
list` (built in an earlier session, alongside hooks and provider plugins), then
what was left when this session picked the milestone back up: deterministic
skill activation actually wired into both CLI paths [SKL-17], a loaded skill's
own `verify:` field taking its place in VER-1's precedence chain, `edgar.run()`
as a documented embedding API [EXT-9, ADR-0051], and the remaining slash
commands `/agents`, `/skills`, `/tools` [CLI-14]. `src/` was at 7,766 of v1's
8,000 when this work began and stands at 7,918 now — 82 lines left for M11.

Three things made the remaining decisions non-obvious: VER-1's precedence order
mixes a session-level source (`--verify`, fixed once) with turn-level ones (which
skill loads depends on that turn's prompt), the module that decides whether a
verify command is even allowed to run was reachable only from `cli/`, and
`agents/` cannot import from `cli/`; and `edgar.run()` living in `src/edgar/__init__.py`
means every `import edgar.anything` runs it first, so it cannot cost what the
rest of the package is not allowed to cost.

## Options and decisions

**1. Where a per-turn verify override lives.** VER-1's order is `--verify`, an
agent's own frontmatter, a loaded skill's frontmatter, then project config. The
first three differ in *when* they are known: `--verify` at session start, an
agent's at `spawn()` time, a skill's only once that turn's prompt and touched
paths are read. (A) Recompute the whole precedence chain inside `core/loop.py`
before every turn. (B) Keep `Runtime.verify` as the single source
`run_turn()` reads, and give each caller (`cli/oneshot.py`, `cli/repl.py`) a
small function that overrides it per turn before calling in. **Decided: B** —
`cli/setup.py`'s new `verify_for_turn(s, rt, activated)` returns `rt` unchanged
when `--verify` was passed (`Setup.explicit_verify`), otherwise chains the
activated skills' `verify:` commands with `skill_verify()` and returns
`replace(rt, verify=Check(...))`. This is the same shape the daily cost cap
already uses (`daily()` overrides `Runtime.budget` per turn); `core/loop.py`
stays a single source of truth and gains no knowledge of skills at all.

**2. Chaining more than one loaded skill's verify command.** `Check.command` is
one shell string; PRD says "each of their commands runs, in load order" without
specifying how. (A) Run each command as a separate verify pass, each with its
own attempt budget. (B) Join them into one shell command. **Decided: B**,
joined with `" && "` in `skills/activate.py`'s `verify_command()`: the first
failure wins, matching how a human would chain checks by hand, and it needed no
new concept in `core/verify.py` — a chained command is still exactly one
`Check`.

**3. Where verify authorisation lives, once a subagent needed it too.**
`agents/spawn.py` needed the same "is this shell command even allowed to run"
check `cli/setup.py`'s `authorise_verify` already did for the main session, but
`agents/` never imports from `cli/` (the architecture doc says only `cli/`
imports from `agents/`). (A) Duplicate the check in `agents/spawn.py`. (B) Move
the logic down into `core/verify.py`, which both `cli/` and `agents/` already
sit below. **Decided: B** — a new `authorise(check, guard, session, bus)` in
`core/verify.py` does the one `guard.check()` call and raises `PermissionDenied`
on a `Deny`; `cli/setup.py`'s `authorise_verify` becomes a thin wrapper over it
for its existing callers, and `agents/spawn.py` calls it directly inside the
same `try` that already turns a subagent's own failure into a tool error
[SUB-8], so a verify command the guard would refuse denies the same way a
provider failure does, not a crash.

**4. `edgar.run()`'s shape, and where it lives.** BLUEPRINT already places it in
`__init__.py` as "a thin async wrapper that builds a session and calls
`run_turn` with the event bus the caller supplies." The one hazard: `__init__.py`
runs on *every* `import edgar.anything`, more eagerly than `cli.main`, which
only the CLI entry point imports. **Decided:** every non-trivial import
(`cli.setup`, `core.loop`, `skills.activate`, the MCP client) is deferred inside
`run()`'s body, behind a comment naming the reason, exactly like
`core/verify.py`'s existing pattern for `Session` and `Guard`; only `Path` and a
`TYPE_CHECKING` block of type-only imports sit at module level. A bare `import
edgar` was checked with `-X importtime` and pulls in none of the NFR-1 banned
packages. The signature adds `home`, `env`, `asker`, `subscribers`, `attached`,
`verify` and `project_exec` as optional keywords beyond EXT-9's required four
(`prompt`, `cwd`, `config`, `mode`, `model`) — the same optional surface
`run_prompt()` already exposes for `-p` — because ADR-0051's supervisor needs
exactly these: an `asker` to answer permission prompts out of band, and
`subscribers` to watch the frozen event format from outside. `config` accepts
either `None` (load it from `cwd` the way `-p` does) or an already-built
`Config` the caller loaded once and reuses across many sessions, with `mode`/
`model` still able to override either. `project_exec` defaults to `True` so
`edgar trust`'s gate on executable project config [PERM-13] holds for a caller
that never thought to ask for it, same as `-p`.

**5. What `/agents`, `/skills` and `/tools` read.** Each is a thin dump of state
the session already built during `setup()`, not a fresh discovery pass (that is
what `edgar tools list` etc. are for outside a session). `/skills` and `/tools`
read `Setup.skills` and `Runtime.tools`; `/agents` reads the `task` tool's own
`.agents` dict off `Setup.tools.get("task")` rather than `Runtime.tools` —
`cli/setup.py`'s `runtime()` always sets `Runtime.tools = Setup.tools`, so the
two agree in every real session, but `Setup.tools` is the one a test harness
that overrides `Runtime.tools` (to add a `slow` tool for cancellation tests)
cannot silently disagree with.

## Consequences

M10 is done: extensions and hooks (built earlier), provider plugins [PRV-14],
deterministic skill activation wired into both CLI paths [SKL-17], a skill's
`verify:` as a VER-1 source authorised the same way as every other source
[VER-4], `edgar.run()` [EXT-9], and the last three slash commands [CLI-14]. The
tour's stop 23 is a built stop; its size table gained a row for `extensions/`
and corrected `cli/` and `skills/`, both of which had drifted past the tour's
own 100-line tolerance.

Against that: `verify_for_turn` and `authorise_verify` are two small functions
doing one job split across `cli/setup.py` and `core/verify.py`, which is the
price of `agents/` never importing `cli/` — acceptable, since the alternative
was either a duplicated authorisation check or bending the import direction.
`edgar.run()`'s optional keywords are a larger surface than EXT-9's bare
four-argument signature; each one is load-bearing for ADR-0051's supervisor and
none is new machinery, so the risk is drift between `run()` and `run_prompt()`
diverging silently over time, not incorrectness today.
