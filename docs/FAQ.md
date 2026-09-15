# FAQ

The questions this project expects, answered before they're asked. Each one
already has a fuller answer somewhere in the docs; this page is the short version
with the link.

## Isn't this just vibe-coded?

Most of the code was written by an AI coding agent. The difference between that
and "vibe-coded" is whether anyone can tell which decisions were made on purpose:
every decision a reasonable person could make differently is an
[ADR](adr/), every session that touched the repository has a dated entry in
[`JOURNAL.md`](JOURNAL.md), and `AGENTS.md` — the instructions the agent works
from — is hand-authored and off-limits to automated edits by its own rule, as its
own first lines say ([ADR-0007](adr/0007-memory-architecture.md),
[ADR-0008](adr/0008-controller-guardrails.md)). Read a few ADRs and a few journal
entries before deciding whether the result looks considered or improvised.

## Why AGPL? Doesn't that kill adoption?

Some, yes — some companies ban it outright, and that's an accepted cost, not an
oversight. The reasoning, including the rejected alternatives (Apache 2.0, MIT),
is in [ADR-0026](adr/0026-licence-agpl.md). Short version: "no hidden calls" and
"read it in an afternoon" are promises about openness, and AGPL is what makes
those promises hold for a hosted fork too, not just a local one. Using, forking
and modifying edgar for yourself carries no obligation at all.

## Why Python, not Rust or Go?

Because the constraint that matters most here is "a person can read the whole
thing in an afternoon," and Python reads closest to the pseudocode comments that
constraint demands. A faster binary would not make the loop, the compaction
pipeline or the permission engine easier to understand — it would just make them
harder to write clearly under the same size budget. Startup latency, the concern
a compiled language would actually fix, has its own answer: a 150 ms budget to
first output byte, enforced in CI on every commit
([ADR-0012](adr/0012-startup-budget.md), [ADR-0019](adr/0019-dependency-budget.md)).

## Isn't this just another agent harness? There are already a dozen.

There are, and most of the design decisions here exist *because* of what people
say about those dozen. [`docs/research/hn-2026-09.md`](research/hn-2026-09.md) is
11,647 Hacker News comments about Claude Code, OpenCode, Codex CLI, Gemini CLI,
Aider and others, read and categorised before this spec's last revision. The
headline — "any model, no hidden calls, nothing is done until it's verified" —
is a direct answer to what that review found people angriest about: hosted
calls nobody configured, token waste, agents that claim success without
checking. [`docs/DECISIONS.md`](DECISIONS.md) walks through what changed in the
spec because of it, point by point.

## The docs are longer than the code. Why?

Because it's a teaching artifact first ([`README.md`](../README.md#what-it-is)
says so plainly) and a teaching artifact that doesn't explain its own decisions
has failed at the one thing it's for. The ADRs are also what keeps an AI coding
agent from re-litigating a settled decision every session — they're load-bearing
for how this project gets built, not decoration around it. `ruff` is configured
to skip `docs/*.md` so the hand-aligned Python blocks inside them never get
reformatted out of readability.

## Why does `-p` need `--mode`?

Because nobody is there to answer a permission prompt in a pipe, so the mode has
to be chosen up front rather than defaulting to something that either blocks on
a prompt that can never resolve, or silently picks a permissive mode for you.
The second one is the failure mode "no hidden behaviour" exists to rule out.

## Why "edgar"?

It's my son's name. He's also my reason for building things at all — this
project included. See ["Why I built it, and how"](../README.md#why-i-built-it-and-how)
in the README.
