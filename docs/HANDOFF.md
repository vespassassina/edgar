# Handoff — start here

For the coding session picking up after v1.0. Written 2026-09-16 by the
planning session; replace it each time work stops mid-task, delete it when the
list is done. Read it first, then the three documents under "Read".

## Where things stand

- **v1.0 is tagged and released.** `v1.0.0` is published on PyPI, `ghcr.io`
  and as GitHub release binaries for all three platforms, 723 tests green,
  `just check` passes. Step 0 below is done, including the fix-forward:
  `docker` raced `publish` on the first real run and was fixed in
  [`.github/workflows/release.yml`](../.github/workflows/release.yml)
  (`needs: [build, publish]`); see `JOURNAL.md`'s 2026-09-16 "docker raced
  publish" entry.
- **M18 is done** (2026-09-16,
  [ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md)): the tour has
  a page per v1 feature, Core's missing stops, a [map](tour/map.html) behind
  `just map`, and a test that fails on a source file with no stop. It added no
  line to `src/`.
- **M19 is done** (2026-09-17,
  [ADR-0059](adr/0059-m19-working-state-as-built.md)): `@path` attachments, plan
  mode and the `todo` tool, `edgar context show`, `edgar sessions compact ID`
  and `edgar config show --resolved`. It is the first milestone since 1.0 with
  `src/` code: `just loc` read 8,374 of 9,500.
- **M20 is done** (2026-09-17,
  [ADR-0060](adr/0060-m20-seeing-and-searching-as-built.md)): images end to end,
  plus web search and git as example files costing no code. `just loc` read
  8,592 of 9,500.
- **M22's code is done and merged** (2026-09-17,
  [ADR-0062](adr/0062-m22-inspection-commands-as-built.md)): the rest of `edgar
  doctor`, `route explain`, `agents list|validate`, `ext validate|add` with
  `skills audit`, and the tour stops. `edgar.testing.contract` [PRV-14]
  was **dropped to v3** for budget — see ADR-0062 §6 for the measurement.
  **What is left of M22 is the 2.0 release itself and its two human criteria
  (a two-week dogfood period, an outside person's PRD §11 checks), and the
  release needs the maintainer's explicit authorisation, as every push, tag
  and release in this project does.** v2's code is otherwise complete.
- **Fixed on `main`, 2026-09-17:** the bug M22's build agent found and correctly
  left alone — `cli/setup.py`'s `runtime()` built the main turn's
  `RoutingContext` with every field bare, so a `[[route]]` rule keyed on `mode`
  could never match it. `mode` and `tools_required` are now the real ones for
  that turn; `tags` and `schedule` stay unset since nothing produces either
  yet. See `JOURNAL.md`'s "fix: the main turn's routing context was always
  bare" entry. `just loc` now reads **9,306 of 9,500**, 194 lines of headroom
  left in the v2 budget.
- **M12 is done and merged** (2026-09-17,
  [ADR-0063](adr/0063-m12-learning-foundations-as-built.md)): autolearn from a
  typed directive, error facts from a tool failure that repeats three times,
  `.edgar/history.md`, `edgar stats`, `edgar history show|distill`, and a
  property test over generated hostile trajectories proving the learning
  boundary holds. `TARGET_TIER` flipped to `"v3"`; `just loc` reads **9,359 of
  9,500** for `src/` without the removable packages (141 lines of headroom for
  all of M13, M14 and M15) and 9,766 of 12,000 for the v3 tier total. One gap
  found while wiring it, out of scope and left for M13: `tools/execute.py`'s
  `_failed()` returns before emitting `ToolFinished`, so validation,
  permission-denied and unknown-tool-name failures never reach the bus and
  cannot become error facts. **M13, the controller, is next.**
- **M21 is done and merged** (2026-09-17,
  [ADR-0061](adr/0061-m21-isolation-as-built.md)): worktree subagents and the
  sandbox backends. Two of
  ADR-0061's flagged decisions matter most and are not yet resolved: §2 says
  the sandbox is a write and network boundary, **not** a read boundary,
  against the roadmap's own wording — a reviewer still has to decide whether a
  read boundary is wanted at all, and if so it is its own milestone; §6 says
  `bwrap` has never been executed by anyone (no Linux machine was available to
  test it), only asserted argv-by-argv against `bwrap(1)`'s documented
  behaviour — a Linux reviewer should run it for real before anyone relies on
  it.
- The plan after 1.0 is re-tiered ([ADR-0057](adr/0057-daily-driver-before-learning.md)):
  **v2 is the daily driver**, M18–M22, ≤ 9,500 lines of code. Learning
  (M12–M15) is v3, the broker and scheduling (M17, M16) are v4. Milestone
  numbers did not change; the order of work is M18, M19, M20, M21, M22, then
  M12.
- The re-tiering docs, M18, M19, M20, M21 and M22's code all landed on `main`,
  each merged after independent re-verification of its ADR's flagged
  decisions by reading the actual source (not the agent's self-report) —
  every one held up. Not yet pushed to `origin`. Next up: Step 0b (the
  dogfood week, the maintainer's own task), then the 2.0 release when the
  maintainer decides to cut it.
- **Four documentation gaps** were found by the cold subagent that verified the
  web-search example; all four are older than M20 and none is fixed. They are in
  `JOURNAL.md`'s M20 entry: there is no `edgar tools validate` to match
  `edgar skills validate`; an HTTP tool's `{slot}` that is missing from
  `[input].properties` loads silently though `EXTENDING.md` documents the rule;
  `edgar trust` lists a tool file by its first comment line rather than its name
  or host; and `EXTENDING.md` never gives the HTTP-tool grammar in full. The
  first two are candidates for M22's inspection work.

## Read, in this order

1. [ADR-0057](adr/0057-daily-driver-before-learning.md): why, and the eight
   decisions. Ten minutes.
2. [`ROADMAP.md`](ROADMAP.md), section "v2 — 2.0, the daily driver", then M22.
   Every item names its files, requirement IDs, test and size.
3. [`AGENTS.md`](../AGENTS.md): the standing rules. Lines mean lines of code;
   pseudocode comments in every file you touch; shallow functions; the tour
   changes in the same commit as the code; `just check` before every commit;
   journal, changelog, roadmap status and an ADR when a decision could go
   another way.

## Step 0 — tag v1.0 · DONE 2026-09-16

`1.0.0` is tagged, released and on PyPI, with the `pyapp` binaries and the
`ghcr.io` image. The `docker` job raced `publish` on the way and was fixed
forward; the journal entry for that day has the detail.

## Step 0b — the dogfood week

Still open. It was meant to run in parallel with M18, which is now done, so it
is the last thing standing between here and M19. The friction list is M19–M22's
real specification; the roadmap items are the best guess without it.

```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

```bash
uv run edgar --model ollama/qwen3:8b
```

Use edgar on edgar: ask it to read a module, fix a test, write a docstring,
run `just check`. Every time you reach for something that is not there, or
something that is there gets in the way, add a line under a `## Dogfood`
heading at the top of [`JOURNAL.md`](JOURNAL.md)'s open items: what you tried,
what happened, which M19–M22 item covers it, or "none". At the end of the week
reorder the items inside M19–M22 by that list. Do not add items; the budget
does not move.

## Step 1 — M18, tours for v1 and the map · DONE 2026-09-16

Built in seven commits, `65033a2..d44f7ed`, one per roadmap item. The pages are
`docs/tour/{index,memory,mcp,agents,extensions,map}.html`, sharing `tour.css`
and `tour.js`; `scripts/tour_map.py` (`just map`) writes `map.json` and
`map.data.js`. Three tests hold it: no source file without a stop, the map
byte-matches what the generator writes, and every page's header links every
other page. `just loc` still reads 8,000 / 8,000. The decisions are in
[ADR-0058](adr/0058-m18-the-tour-pages-and-the-map-as-built.md).

What a later milestone needs to know:

- Every page uses the same stop shape,
  `<article class="stop( planned)?" id="(\w+)" data-files="([^"]+)">`, so one
  test covers all of them. A new `.py` under `src/edgar` fails the suite until
  some stop names it; `__init__.py` is exempt except `src/edgar/__init__.py`.
- Run `just map` after changing `src/edgar` or any stop's `data-files`, or the
  byte-match test fails. The generator's `V1_PREFIXES` / `V1_FILES` table is
  hand-maintained: a file a new milestone adds lands in Core unless listed.
- `map.html` reads `window.EDGAR_MAP` from `map.data.js`, not `map.json`, so it
  works opened as a local file. Both are generated from the same function.

## Step 2 — M19, working state · DONE 2026-09-17

Built in six commits, `41052a8..` on the M19 branch, one per roadmap item plus
this trace. New files: `context/attach.py`, `context/working.py`,
`tools/builtin/todo.py`, `cli/inspect.py`; the tour page is
[`tour/working.html`](tour/working.html). `TARGET_TIER` in
`tests/support/budget.py` is now `"v2"`, so `just loc` reports against 9,500 and
reads 8,374. The decisions are in
[ADR-0059](adr/0059-m19-working-state-as-built.md).

What a later milestone needs to know:

- Working state (plan, todos, the mode to give back) lives on the `Session` as
  `session.working`, **not** in the transcript. `context/builder.py`'s `build()`
  calls `place()` last to render it just above the current turn. If you add a
  compaction stage, it does not need to know about working state — but anything
  that measures the prompt does: `compact()`'s `size()` counts the rendered
  block, and a new measurer that forgets it will under-read.
- Plan mode is `session.mode == "read-only"` plus `working.previous_mode`.
  There is no plan-mode flag in `permissions/`, and there must not be one:
  `decide()` stays a pure function of tool, subject and mode. Only `/plan`,
  `--plan` and `/go` call `enter()`/`leave()`.
- The three inspection commands share `cli/inspect.py`. M22's `route explain`,
  `agents list|validate` and the rest of `doctor` belong there too, not in
  `cli/admin.py`.

## Step 3 — M20, seeing and searching · DONE 2026-09-17

Built in ten commits, `e512b90..33e1d90`, one per roadmap item. No new module:
every image change extends a file that already existed. The tour page is
[`tour/media.html`](tour/media.html). `just loc` reads 8,592 of 9,500 (218
added against ~200 estimated). The decisions, three of them flagged for extra
review, are in [ADR-0060](adr/0060-m20-seeing-and-searching-as-built.md).

What a later milestone needs to know:

- **The `ImageBlock` shape.** Frozen and slotted, four fields and only four:
  `media_type`, `ref` (the blob path, posix), `width`, `height` (both 0 when the
  header could not be parsed). The bytes are never in the block, never in the
  transcript and never in the event stream — only under
  `sessions/<id>/blobs/`. Anything that needs the bytes calls `encoded()` in
  `providers/http.py`, which base64s for one request and raises `ProviderError`
  if the blob is gone. If you are tempted to add a fifth field, the test that
  kept the others out was "does serialisation or token counting read it?", and
  the asymmetry is in ADR-0060 §1: adding later is additive, removing is a
  migration.
- **`Message.images`** gathers pictures from a message's own blocks *and* its
  tool results. Read that instead of walking blocks; counting, eliding and both
  adapters all do.
- **The capability-gating pattern**, which is the one to copy for any future
  capability. The row goes in `providers/quirks.py` — a capability is data, never
  a branch. The refusal goes in `providers/routing.py` next to
  `check_capabilities()` and `check_images()`, and fires **where the model is
  chosen**, from `cli/oneshot.py` and `cli/repl.py`, before a request is built
  or a cent is spent [ROUTE-6]. When the same capability can also be hit
  mid-turn, once the model is already chosen, carry it on `ToolContext` (see
  `ToolContext.images`, set from `rt.provider.capabilities` in `build_context`)
  and have the tool answer with a plain sentence rather than an error: the call
  worked, and the model decides what to do next.
- **`context/tokens.py` stays pure.** `image_tokens()` prices by geometry and
  knows two rules, one for `anthropic` and one for everyone else, chosen by the
  `family` string. A new provider family with a third pricing rule goes here, and
  every caller already passes `family` through `approx_message_tokens()`.
- **Compaction has exactly one function that knows where a turn may be cut**,
  and `_stub()` is where a new block type gets its elided form. Do not add a
  second pass; ADR-0060 §2 has the argument. Whatever you add must be
  idempotent and must replace a tool result's text and its images together.
- **`core/loop.py` is at 200/200 lines of code**, its hard cap, with no
  headroom. Anything M21 or M22 adds to a turn has to buy its lines back inside
  the file: the M20 technique was module-level type aliases keeping signatures
  on one line, and narration moved from docstrings into `#` comments, which the
  budget does not count.
- **Web search and git are files, not code**, under `examples/`. If a future
  capability fits the frozen command-tool, HTTP-tool, skill or hook formats, it
  should arrive the same way; ADR-0060's last section says why a built-in
  `web_search` was refused (PRV-15: it would need a default host).

## Step 4 — M21, isolation · DONE AND MERGED 2026-09-17

Built in three commits on `feat/m21-isolation`, one per roadmap item plus this
trace. New files: `agents/worktree.py` and the `sandbox/` package
(`base.py`, `none.py`, `bwrap.py`, `seatbelt.py`); the tour page is
[`tour/isolation.html`](tour/isolation.html). 277 lines of code against ~350
estimated, `just loc` 8,869 of 9,500, `just check` green on macOS with 858 tests.
The decisions are in [ADR-0061](adr/0061-m21-isolation-as-built.md), four of them
flagged for extra review.

The tour page was created in the **first** commit rather than the last, with the
sandbox stops marked `planned`, and grown as the code landed. That is a
deliberate departure from "the tour is item 3": `just check` must be green at
every commit, and `test_tour.py` fails the moment a `.py` exists with no stop.

What a later milestone needs to know:

- **How `sandbox/base.py` is extended for `container`.** Add `container.py` with
  a class carrying `name`, `available()` (does `docker` or `podman` answer?) and
  `wrap(argv, *, cwd, writable, network) -> list[str]` returning
  `["docker", "run", "--rm", …, "--network", "none", …, *argv]`, then add an
  instance to `_all()` — **at the end**, because `best()` walks the list backwards
  and the order *is* the ranking. Nothing else changes: `backend()`, the config
  literal in `config/schema.py`, `doctor` and every call site already name it.
  The port is pure on purpose (ADR-0061 §1); a backend that needs to supervise
  its own process does not fit, and widening the port should be argued in the
  open rather than bolted on.
- **`agents/worktree.py`'s cleanup contract, which must not be loosened.**
  `finish()` treats *any* non-empty `git status --porcelain` as dirty, keeps the
  tree, and returns a summary naming the path, the branch, the diff stat and the
  removal command. The tree is only ever removed when it is clean, always from
  the parent repo, and **never** forced. Nothing deletes a worktree later, and
  nothing should start: a kept tree holds work a subagent did that nobody has
  read yet. If you want a human to *find* kept trees more easily, add a line to
  `edgar doctor` that lists them — do not add a registry file, and do not add
  automatic cleanup.
- **`create()` refuses rather than degrades.** Outside a git repository, or on
  any failure creating the tree, the subagent does not run at all. Any future
  isolation mode should copy that: a quiet fallback to sharing the tree is the
  failure this feature exists to prevent.
- **A sandbox never decides.** The network answer comes from
  `permissions.policy.network_allowed(mode, tainted)`, is recomputed per call in
  `tools/execute.py` (taint can be set by an earlier call in the same turn) and
  rides on `ToolContext.network`. The writable set is `[cwd, blob_dir]`, built by
  the harness. If a future feature needs another writable root, it goes in
  `confined()` in `tools/builtin/shell.py` and nowhere else.
- **`.edgar/worktrees/` must stay ignored** (it is in
  `templates/gitignore.fragment`). Without `.edgar/` ignored, a worktree always
  reads dirty and is therefore always kept: safe, but useless.

## Step 5 — M22, inspection · CODE DONE AND MERGED 2026-09-17, RELEASE NOT STARTED

Built in five commits on `feat/m22-inspection-commands`, one per roadmap item:
`c3e7d18` doctor, `d4da60f` `route explain`, `cb03b77` `agents list|validate`,
`3a06545` `ext validate|add` with `skills audit`, `8d9290b` the tour stops. New
files: `skills/audit.py` and `extensions/validate.py`; everything else extends
`cli/doctor.py`, `cli/inspect.py`, `cli/admin.py`, `agents/discovery.py` and
`providers/routing.py`. 436 lines of code against ~440 estimated, `just loc`
9,305 of 9,500, `just check` green on macOS with 869 tests. The decisions, three
flagged for extra review, are in
[ADR-0062](adr/0062-m22-inspection-commands-as-built.md).

**The 2.0 release is deliberately not started.** No version bump in
`pyproject.toml` or `src/edgar/__init__.py`, no tag, no `CHANGELOG.md` version
header — everything new is under "Unreleased". The maintainer authorises a
release every time; nothing here presumes it.

What a later milestone needs to know:

- **`edgar doctor` is offline by default and must stay that way.** A check that
  wants the network goes behind `--network`, and the skipped line has to say what
  was not checked. `--network` calls each provider's `models()`, which is an
  authenticated call (no tokens, but it needs the key) — if you add a check that
  needs no credentials, say so on its line rather than letting the two blur.
- **A remote MCP server is not probed, on purpose.** The handshake in `edgar mcp
  test NAME` is the only probe worth making, and duplicating it in `doctor` would
  be a second copy of the client. If M16 ever lands, its tick check goes in
  `cli/doctor.py`'s comment block *and* its print order, which are kept in step.
- **The danger table in `skills/audit.py` is data.** A new pattern is a row in
  `DANGERS` plus a test, never a branch, and the ids (`SA-D1`…) are referenced by
  the docs, so append rather than renumber. The conformance ids (`SA-1`…) set the
  exit code; danger ids never do.
- **ADR-0042's `--review` is unbuilt but its rule still binds.** If anyone adds
  the opt-in model review, it may add findings and must not set the exit code or
  the default answer. A skill that can argue with its own audit is the failure
  the whole design exists to prevent.
- **`ext add` never lands a partial copy**: stage beside the destination, then one
  `rename`. Any future installer (a git URL, say) must keep that shape, and must
  keep the order — validate, audit, show, ask, only then write.
- **`skills/discovery.py`'s `read()` is public now** so the audit and a session
  load a skill with the same rules. Keep it that way; two readers would let an
  audit pass what discovery rejects.
- `cli/inspect.py` is at 163 lines of code and holds five commands. It is the
  home for inspection commands, per M19's note, but it is now big enough that a
  sixth should probably start its own module.

One open offer, still open: the roadmap's "Never yet" item 9 allows the
`container` sandbox backend if budget remains. 195 lines of code remain, and it
is perhaps 25 on the port as it stands; **ask before building it**, and weigh it
against PRV-14, which was dropped and has the better claim.

## Step 6 — M12, learning foundations · DONE AND MERGED 2026-09-17

Built in five commits on `feat/m12-learning-foundations`: events (`ToolFinished`
gained `error: ErrorRecord | None`, plus `PromptTyped` and `SkillsActivated`),
the tier flip, the `learning/` package (`experience.py`, `learner.py`,
`error_facts.py`, `history.py`, `cli.py`) with the tour page and stop `s31`
turned into a link, the tests including the property test, and the trace. New
package: `src/edgar/learning/`; new tour page `docs/tour/learning.html`. 407
lines of code against the budget, `just loc` 9,359 of 9,500 (`src/` without the
removable packages) and 9,766 of 12,000 (v3 total), `just check` green with 917
tests. The decisions are in
[ADR-0063](adr/0063-m12-learning-foundations-as-built.md).

What a later milestone needs to know:

- **The boundary is a subscription, not a filter.** `Learner` reads exactly one
  event, `PromptTyped`, and only at `depth == 0`; `ErrorFacts` reads exactly one
  field, `ToolFinished.error`. Neither opens a file, reads a transcript or
  scans text for anything unsafe — there is nothing to filter, because the
  excluded sources (tool output, model text, a subagent's prompt, piped stdin,
  an `@path` body) physically cannot reach either event. Copy this shape for
  M13's controller and M14's synthesiser: subscribe narrowly, never guess.
- **The property test is the one to extend, not duplicate.**
  `tests/property/test_learning_boundary.py` drives a generated trajectory of
  typed lines, model text, tool calls and failures — with attacker-chosen text
  tainted so it can be told apart — through the real subscribers on a real bus,
  and asserts no tainted byte ever reaches an active fact. A future learning
  source should be added as a new step kind here before it is trusted.
- **`ToolFinished.error` has a real gap, left for M13.** `tools/execute.py`'s
  `_failed()` helper returns a result directly, before `ToolStarted` or
  `ToolFinished` is ever emitted, for three failure kinds: unknown tool name
  (`not_found`), schema validation (`validation`), and permission/hook denial
  (`permission_denied`). `ErrorFacts` can never see these three kinds. This
  does not break the core ADR-0017 example (a shell command's binary-not-found
  failure happens inside real execution, past `ToolStarted`, a different code
  path) — but it is a real blind spot if M13 wants to learn from denials.
- **`edgar stats` and `edgar history show|distill` live in `learning/cli.py`**,
  not beside the other inspection commands in `cli/inspect.py`, because
  `tests/unit/test_architecture.py`'s import-graph check catches a
  function-level `import edgar.learning` exactly like a top-level one.
  `cli/main.py` dispatches to it by name with `importlib`. Any future v3/v4
  command needs the same shape.
- **`history distill` can never produce an active fact**, not by a check but by
  construction: it saves with provenance `"distilled"`, which is not in
  `memory/store.py`'s `ACTIVE_FROM`, so the store puts it in `pending` no
  matter how many times a pattern repeats. Do not add `"distilled"` to
  `ACTIVE_FROM` without a new ADR — that is ADR-0017's rule, not an oversight.
- **`.edgar/history.md`, `.edgar/history.1.md` and `.edgar/learning.db` are
  gitignored by default** (OQ-1, resolved in `templates/gitignore.fragment`):
  one person's sessions, not the project's shared state.
- MEM-14's out-of-band model call to condense a long prompt was **cut**:
  `history.py`'s `condense()` keeps the first 40 words and says how many were
  dropped, no model call. The verbatim prompt is kept in `learning.db`, so a
  later milestone can add the call over the same data if it earns its keep —
  see ADR-0063's "What was cut" section, since this is the one place the build
  agent flagged as a decision the maintainer might make differently.

## Proposed diff to `AGENTS.md` (maintainer applies by hand)

`AGENTS.md` is hand-authored (ADR-0007, ADR-0008). Rule 10 and the size table
still describe the removable tier as "v2". Proposed wording:

```diff
-10. **Tier isolation.** Core and v1 code never imports `edgar.controller`,
-    `edgar.learning`, `edgar.schedule`, `edgar.broker` or
-    `edgar.providers.escalation`. v2 attaches
-    through the post-turn gate and the event bus. [NFR-12, ADR-0015]
+10. **Tier isolation.** Core, v1 and v2 code never imports `edgar.controller`,
+    `edgar.learning`, `edgar.schedule`, `edgar.broker` or
+    `edgar.providers.escalation`. v3 and v4 attach through the post-turn gate
+    and the event bus; v2, the daily driver, extends Core and v1 packages and
+    is not removable. [NFR-12, ADR-0015, ADR-0057]
```

```diff
-| `src/` total | Core ≤ 5,000 · v1.0 ≤ 8,000 · v2.0 ≤ 11,000 LOC |
+| `src/` total | Core ≤ 5,000 · v1.0 ≤ 8,000 · v2.0 ≤ 9,500 · v3.0 ≤ 12,000 · v4.0 ≤ 13,000 LOC |
```

`CLAUDE.md` is already updated on this branch.

## Proposed diff to `src/edgar/templates/config.toml` (maintainer applies by hand)

The shipped config template is hand-authored under the same rule as
`config.toml` itself (ADR-0008), so M21 did not edit it. `[shell] sandbox` is
read and honoured by the code, but a fresh `edgar init` does not mention it.
Proposed, under the existing `[shell]` block:

```diff
 [shell]
 program = "auto"
+# The walls a shell call, a command tool and the verify command run inside.
+# "none" (the default) is a plain subprocess; "bwrap" needs bubblewrap on Linux,
+# "seatbelt" uses macOS's sandbox-exec. A backend you name but do not have ends
+# the session with an error rather than running unconfined. It confines writes
+# and the network, not reads. `edgar doctor` says which is best here. [PERM-15]
+# sandbox = "none"
```

## Resume commands

```bash
git switch main
```

```bash
just check
```

```bash
just loc
```
