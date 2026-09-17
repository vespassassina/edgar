# ADR-0062 — M22's inspection commands, as built

**Status:** Accepted · 2026-09-17 · Implements CFG-5, ROUTE-9, EXT-3, SKL-18;
amends ADR-0042 (the `--review` half is not built) and defers PRV-14

## Context

M22 is the last code milestone of v2: the commands cut from 1.0 by ADR-0053 that
explain what edgar would do before it does it. The roadmap budgeted about 440
lines of code for six items, with the standing rule that the last items yield
first if the tier budget is short. v2's budget is 9,500 lines of code and does
not move.

Four of the six items were underspecified in ways that a reasonable person could
settle differently. This records how they were settled, and what was dropped.

## Decisions

### 1. `edgar doctor` is offline unless you ask, and says what it did not check

The roadmap asked for "each configured MCP server reachable" and "`--network` to
try each provider endpoint". Reachability has no single meaning, so each kind of
server gets the check that is honest for it:

- **A stdio MCP server** is checked with `shutil.which` on its `command`. That is
  the whole failure mode worth catching before a session — a command that is not
  installed — it costs nothing and it cannot hang.
- **A remote MCP server is not probed.** The only probe that means anything is the
  initialise handshake, which `edgar mcp test NAME` already performs, with auth
  and a timeout. A TCP connect would prove a socket opened, not that the server
  speaks MCP, and it would make a bare `doctor` reach the network. So the line
  names the server and points at `edgar mcp test NAME`.
- **Provider connectivity moved behind `--network`.** It was unconditional before
  M22, which meant `edgar doctor` opened sockets nobody asked it to. It now runs
  only with `--network`, and the skipped line says how to ask for it.

What `--network` actually does: it calls each configured provider's `models()`.
That is an **authenticated** request for most providers — it needs the key the
`cred` check just reported on, and it fails with an auth error when the key is
wrong, which is useful but is not a pure reachability test. It lists models, so
it costs no tokens, and it is not a completion: no paid inference happens. It
inherits the provider adapter's own timeout rather than setting a second one.
The alternative — an unauthenticated TCP or HEAD probe — was rejected because
knowing a provider's endpoints belongs inside `providers/`, and duplicating that
knowledge in `cli/doctor.py` is exactly the kind of second copy the harness
avoids elsewhere.

Tick installation is **not** checked: M16 does not exist yet, so there is nothing
to check. The comment block at the top of `cli/doctor.py` lists the checks in
print order and names these three limits, so the file says what it does not do.

### 2. `route explain` shows the context a turn really builds

`cli/setup.py`'s `runtime()` passes a bare `RoutingContext()` for the main role,
so a `[[route]]` rule keyed on `mode`, `tags` or `schedule` can never match a main
turn. `route explain` could have built a richer context and printed prettier
output. It does not: it prints the verdict for the context the real path builds,
and the rule-by-rule lines show such a rule as skipped. Making the command lie
about routing to make routing look better would defeat the command. The gap is
edgar's, not the command's, and it is now visible.

### 3. `agents validate` points at a line

`agents/discovery.py` raised problems with the file path only. It now prefixes
each with `path:line`, found by matching the offending key's name against the
file's lines (`line_of`). It falls back to line 1 when the key cannot be located,
which is honest about being a lookup rather than a parser position.

### 4. The skill audit: ADR-0042 minus the model review

Built as ADR-0042 specifies, with one omission. Conformance rules SA-1..SA-5
(loads, description says when to use it — reusing `skills.discovery.lint` rather
than a second copy of it, relative paths stay inside the folder, body under a
token size, and under `--strict` SKL-16's four sections) set the exit code.
Danger rules SA-D1..SA-D14 are a table, one row per pattern, covering every item
ADR-0042 lists: a download piped into a shell, `sudo`, recursive deletes, `eval`,
yolo and `EDGAR_YOLO`, `--no-verify` and "don't ask", "don't tell the user",
zero-width and bidi characters, HTML comments, long base64 runs, credential
locations, every host named, paths that leave the folder, and every bundled
script or executable with the programs it calls.

**`--review` is not built.** It is the only part of ADR-0042 that costs money,
and by ADR-0042's own load-bearing rule it never sets the exit code or the
default answer — so it is the part that can be missing without changing a single
verdict. The v2 budget is the reason, and the split it protects is preserved in
code and comment: if it ever lands, it may add findings and must not decide.

**`--diff` is partial.** ADR-0042 lists normalised frontmatter, hidden characters
removed and missing sections added. Hidden characters and missing sections are
implemented; frontmatter normalisation is not, because the loader either accepts
frontmatter or rejects it with a reason, and there is no normal form to write.

`skills validate` is untouched and stays the quick check.

### 5. `ext add` cannot land a partial copy

The copy goes to a staging folder beside the destination and is then moved with
one `rename`. The destination either does not exist or is the whole extension; a
crash mid-copy leaves the staging folder, which is removed on the way out and is
not on the discovery path in any case. An existing destination is refused rather
than merged into, so nothing is ever half-replaced either.

The gate order is: validate, refuse on any problem; audit every skill it would
copy and print the report; refuse on a conformance finding; ask, defaulting yes
when clean and no on a danger finding; only then copy. With no terminal, a danger
finding is refused unless a human passed `--yes`. The machine never widens.

### 6. `edgar.testing.contract` [PRV-14] is dropped from M22

It was the fifth of six items, and the rule is that the last items yield first.
The measured reason: the contract suite is 265 lines of test code, which as
`src/edgar/testing/contract.py` would cost roughly 200 lines of code against the
tier — against a roadmap estimate of 70, because the estimate was made before the
suite existed. After the other items, 195 lines of code remained. It does not
fit, and the budget does not move.

It is not lost: `tests/contract/test_provider_contract.py` still runs for every
built-in provider, and a plugin provider's author can copy it. Packaging it as an
importable kit moves to v3, where the budget can carry it.

## Consequences

- `edgar doctor` with no flags never opens a socket, which makes it usable on a
  plane and in CI, and the two things it therefore does not verify are printed
  rather than implied.
- A clean `skills audit` means no known pattern matched. Nothing in the code,
  the docs or the tour says more than that.
- v2 closes at 9,305 of 9,500 lines of code with PRV-14 outstanding.
- **The 2.0 release is not part of this work.** The roadmap's release step and
  M22's two human "Done when" criteria — two weeks of real use, an outside
  person's run at PRD §11 — are untouched, so M22 is not Done.
