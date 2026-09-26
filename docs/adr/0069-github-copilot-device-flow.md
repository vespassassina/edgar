# ADR-0069 — Ship GitHub Copilot now, and keep it out of the non-removable budget

**Status:** Accepted · 2026-09-26 · Amends ADR-0043's shipping gate

## Context

ADR-0043 accepted GitHub Copilot as a provider but gated shipping on the
maintainer checking GitHub's terms or asking GitHub whether a registered app
may call the Copilot endpoint directly. That check has not happened. The
maintainer chose to override the gate and build now rather than wait
("override it — build anyway"), accepting the risk ADR-0043 already named:
GitHub can withdraw access, and if it does, the provider is removed in the
next release with every other provider unchanged.

Building it landed the feature at 9,582 of the 9,500-line "src/ without
removable packages" budget (v2's cap, which v3 and v4 must also fit outside
their own removable packages, ADR-0057). The device flow, its `Device` row,
and the static Copilot quirks entry are real code, correctly placed by
ADR-0043's estimate of "about 80 lines," but v2 has no room left for a whole
new vendor's worth of it.

## Options

**A. Give the feature its own removable module, reached by name.** Move the
device-flow engine and the Copilot `Quirks` row into a new file, excluded
from the budget the same way `providers/escalation.py` already is, and reach
it from non-removable code only through `importlib.import_module` by string
— never a static import, since `static_import_graph` (the tier-isolation
test) parses import statements, not string arguments.

**B. Give Copilot its own adapter module, mapped directly in
`registry.BUILTIN`.** This would let the whole provider, adapter included,
live in the removable file, saving a few more lines. Rejected: `resolve()`'s
`adapter = import_module(module)` line for a `BUILTIN` name has no
try/except. On a stripped v3/v4 build, `providers/github_copilot.py` would
be gone, and the module lookup would throw an uncaught `ModuleNotFoundError`
instead of the intended clean, honest degradation. NFR-12 requires the suite
below v3/v4 to still pass after CI deletes those packages; this alternative
would leave a live landmine no existing test exercises.

**C. Shrink the feature instead of moving it.** Cut the device flow down to
close the gap without a new file. Rejected: the flow is RFC 8628, already
about as small as it can be while staying readable, and squeezing it further
trades clarity for a few lines with no structural benefit.

**D. Defer to a later tier's milestone instead of shipping now.** Rejected
by the maintainer's own override of the ADR-0043 gate: the ask was to build
now, not to wait for a natural v3/v4 milestone.

## Decision

**A.** GitHub Copilot's device-flow engine, its `Device` dataclass, and its
`Quirks` row all live in `src/edgar/providers/github_copilot.py`, added to
`REMOVABLE_PATHS` in `tests/support/budget.py` and to the `V2` tuple in
`tests/unit/test_architecture.py`, the same treatment `providers/escalation.py`
already gets. This is a budget placement, not a tier placement: Copilot is a
Core/v1-shaped feature (a provider and a login flow) that happens to be
excluded from the line count the way v3/v4 code is, because v2 has no space
for it and moving the whole feature to a real v3/v4 milestone would be
dishonest about what it is.

The seam back from non-removable code is `quirks.py`'s `_optional_row(name)`,
which returns `None` for every name but `"github-copilot"` and otherwise
resolves the row by string through `import_module`, catching
`ModuleNotFoundError` so a stripped build falls through to the ordinary
"unknown provider" error rather than crashing. `Quirks.device` is typed
`Any | None` so `quirks.py` itself never imports the `Device` dataclass.
The adapter stays the shared, non-removable `openai_compat.py`
(`registry.BUILTIN["github-copilot"]` maps to `_OPENAI`, unchanged): only the
row is optional, never the module resolution that option B would have made
optional and unsafe.

`openai_compat.py`'s `_headers()` merges `quirks.extra_headers` before
authentication headers, a small generic field kept in the shared `Quirks`
because it is genuinely reusable (any future OpenAI-compatible vendor with a
required custom header benefits), not specific to Copilot.

## Consequences

- The measured overage went from 82 lines to 12 (9,512 / 9,500 on
  "src/ without removable packages"). The residual 12 lines are the
  `_optional_row` seam and `extra_headers` support in `quirks.py` and
  `openai_compat.py` — code that must stay non-removable because every
  provider's `Quirks` row and every request's headers are built there,
  Copilot included.
- **Load-bearing:** `_optional_row`'s name check (`if name != "github-copilot":
  return None`) is deliberately explicit, not a generic
  `providers.<name>`-guessing lookup. A generic version would silently pick
  up any future `providers/<name>.py` module for an unrelated provider name
  that happens to share it, which is a correctness risk for a few lines of
  savings. Widening it needs its own reasoning, not just convenience.
- CI's deletion of v3/v4 packages does not touch `providers/github_copilot.py`
  today, since it is reached the same way `providers/escalation.py` is, but
  it is excluded from the v2 budget on that same basis: a future audit of
  "removable" should not assume everything in `REMOVABLE_PATHS` is a v3/v4
  learning or scheduling feature. Some of it, like this one, is a normal
  feature placed there for budget, not tier, reasons.
- ADR-0043's shipping gate (checking GitHub's terms before release) is still
  open. This ADR overrides the gate for building and merging to a feature
  branch, not for a public release; the maintainer still owns confirming the
  terms before `edgar login github-copilot` reaches a tagged release.

## Rejected alternatives

**B** would be revisited if `registry.resolve()` grows a general
try/except around `import_module(module)` for every `BUILTIN` name, turning
a missing adapter module into the same clean "unknown provider" error a
missing row gets today. That would make a dedicated Copilot adapter module
safe, and worth revisiting if the shared adapter ever needs a Copilot-only
branch that ADR-0020 would otherwise forbid.

**C** would be revisited if the device flow needs to change shape anyway
for an unrelated reason (a second vendor's device flow, say), since
generalizing it might shrink both call sites at once.
