# ADR-0054 — M9, subagents as built

**Status:** Accepted · 2026-09-15 · Completes M9; refines ADR-0006, ADR-0013,
ADR-0021; implements ROUTE-6, SUB-9

## Context

M9 adds subagents: the `task` tool re-enters `core/loop.py` with a fresh
transcript, a narrowed policy and an inherited budget (ADR-0006 said a subagent
is never a second engine), routing rules and sideways fallback for the three
model mechanisms ADR-0013 keeps apart, and consecutive `task` calls fanning out
concurrently through `tools/execute.py`'s `execute_many()` [TOOL-12]. Most of
this was built in an earlier session. What was left when this session started,
after ADR-0053's second trim narrowed the milestone's remaining scope: the
multi-row status bar for concurrent subagents [SUB-9], example agents in
`examples/`, and wiring `check_capabilities` [ROUTE-6] into product code — a gap
the simplification pass in commit `de9a027` found: the function was
exhaustively unit-tested but never called. `src/` is at 7,374 of v1's 8,000
after this work.

Two things made the remaining decisions non-obvious: a status line rebuilt
statelessly from events cannot show a second thing running without deciding how
many lines redraw and how the block shrinks back down, and a model with no tool
support needs to fail once, clearly, rather than confusingly on whichever turn
first tries to call one.

## Options and decisions

**1. Where a model's tool support is checked.** `check_capabilities(selection,
tools_required=…, has_tools=…)` in `providers/routing.py` already raised
`ConfigError` correctly; the question was only where to call it. (A) Inside
`core/loop.py`, so every path is covered by one call. (B) At every place a model
is chosen. **Decided: B — at `agents/spawn.py`'s one `spawn()` and
`cli/setup.py`'s one `runtime()`**, both of which already resolve a
`Selection` to a provider before doing anything else. The loop never resolves a
model itself, so a check inside it would need the same information passed in
again for no benefit. The two callers diverge in what a failure returns:
`spawn()` catches `EdgarError` and returns `ToolResult(error="validation")`,
because a subagent's failure is a tool result the parent model reads and can
recover from — a subagent asking for the wrong model is not fatal to the
session. `runtime()` lets `ConfigError` propagate, because choosing the main
model wrong is the same class of mistake as a bad config file, and the existing
handlers (`main.py`'s top-level `except EdgarError`, `/model`'s own handler in
`cli/slash.py`) already turn that into a clear message and stop, rather than
starting a turn that will fail confusingly on its first tool call.

**2. How a multi-row status line stays a pure function of events.** `Status`
already rebuilds one line from nothing but the event stream (CLI-5); adding a
second, variable-height row for each running subagent without breaking that.
(A) Track subagents in a separate collaborator the REPL and `-p` both query
alongside `Status`. (B) Fold subagent state into `Status` itself, keyed by
`agent_id`. **Decided: B.** Every event already carries `depth` and `agent_id`
(a subagent's bus is `ctx.bus.scoped(agent_id=agent.name, depth=depth)`), so
`Status.__call__` dispatches any event with `depth > 0` to a new `_subagent()`
method that keeps a `dict[str, _Row]` — phase, tool count, start time — one
entry per `agent_id`, inserted on its first event and dropped on its
`TurnFinished`. Consecutive `task` calls fan out [TOOL-12], so more than one row
can exist at once; each is independent, and a subagent's own events never touch
the main row's `phase`, `tools` or `started` fields. `Status.line()` — the main
row — is unchanged, byte-for-byte, so no existing caller or test needed to
change; `rows()` is new and returns `[line(), *one row per agent]`.

**3. Redrawing a block that grows and shrinks.** The REPL's bottom toolbar is
just `"\n".join(rows())` — prompt_toolkit owns redrawing it. The `-p` path's
`StderrLine` writes raw escapes to a terminal and has to manage that itself as
subagents start and finish mid-turn. **Decided:** track `self._drawn`, the row
count from the last redraw; move the cursor up `_drawn - 1` lines, rewrite each
row with `\r\x1b[2K` (clear the line), and finish with `\x1b[J` (clear from the
cursor to the end of the screen) so a block that just shrank — a subagent
finished — never leaves a stale row hanging below the new, shorter block.

**4. Whether an example agent needs a CLI command to prove it is real.**
`examples/README.md`, before this session, claimed "the `task` tool appears on
its own" once an agent file exists, but `cli/admin.py`'s `_tools()` (behind
`edgar tools list`) called `toolset()` directly and never discovered agents or
added a `TaskTool` — unlike `cli/setup.py`'s `setup()`, which does both, so a
real session and the listing command disagreed. **Decided: fix `_tools()` to
match `setup()`**, discovering agents and constructing a `TaskTool` behind a
`Guard` built the same way (`Policy` from the loaded config, a `Store` at
`.edgar/edgar.db`, no `asker` since nothing is run) whenever `.edgar/agents/`
holds a file. This is not new scope — `edgar agents list` stays cut
([ADR-0053](0053-what-1-0-actually-ships.md)) — it is `edgar tools list`
telling the truth about what a session would actually get, which is the thing
the command already promises for every other tool source. `examples/agents/
code-reviewer.md` was added: `read-only` mode, four tools (`read`, `ls`,
`glob`, `grep`), so it can review and report but never edit or run a shell
command; an e2e test copies it into a project and asserts `edgar tools list`
shows `task`.

**5. The open question from the journal: does `Guard`'s asking lock really
serialise concurrent prompts?** `Guard._ask()` holds `self._lock` (an
`asyncio.Lock`) around the one call to `asker()`, so two subagents fanned out by
`execute_many()` [TOOL-12] that both hit an `Ask` decision cannot both be
mid-prompt at once. This holds by construction, not by the fan-out tests, which
never exercised it: edgar runs one event loop per session and `asyncio.Lock`
serialises coroutines within that loop unconditionally — there is no thread or
process boundary for two `task` calls to cross, so nothing about "real
concurrency" changes the guarantee an `asyncio.Lock` already gives a
single-threaded event loop. **Settled: no code change and no new test are
needed** — the property was never in doubt, only unexercised; a test asserting
it would be testing `asyncio.Lock` itself, not edgar.

## Consequences

M9 is done: subagents, routing rules, fallback, the multi-row status bar,
example agents, and a model with no tool support is refused once, at selection,
with a clear error, instead of failing on whichever tool call happens first.
Against that: `Status` now knows about `agent_id` and `depth`, which is a little
more than the main-session line strictly needs, and `_tools()` constructing a
`Guard` purely to decide whether `task` would exist is a small duplication of
what `setup()` already does — accepted because the alternative (a listing
command that under-reports) is worse, and the two now agree because the same
`discover_agents()` / `TaskTool` construction runs in both.
