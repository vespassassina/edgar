# ADR-0026 — License edgar under AGPL-3.0-or-later

**Status:** Accepted · 2026-09-13 · Replaces the Apache 2.0 entry in PRD v0.4

## Context

The spec said Apache 2.0 without an ADR behind it. When the public repository was
created it was initialised with AGPL-3.0, and the maintainer chose to keep that.
A licence is hard to change once outside contributions arrive, since every
contributor holds copyright in their part, so the choice is recorded here.

What makes it non-obvious: edgar wants two things that pull in different
directions. It wants to be forked and changed (a teaching artifact, small enough to
read), and it has an embedding API (`edgar.run()`, `--events`, EXT-9) that invites
people to build products on top of it.

## Options

**A. Apache 2.0.** Permissive with a patent grant. Anyone can embed, modify and
ship edgar, including in closed products and hosted services, without sharing
changes. Maximises adoption, especially by companies. Improvements made in hosted
forks never have to come back.

**B. MIT.** Like Apache without the patent grant or the notice requirements.
Shortest text; weaker protection for users and contributors on patents.

**C. AGPL-3.0-or-later.** Strong copyleft that also covers network use: anyone who
distributes a modified edgar, or lets others use a modified edgar over a network,
must offer the source of their version under the same licence. Private use and
modification carry no obligation. Keeps every public derivative open, including
hosted ones.

## Decision

**AGPL-3.0-or-later.** `LICENSE` holds the GNU AGPL v3 text; `pyproject.toml`
declares `license = "AGPL-3.0-or-later"`. "Or later" follows the FSF's
recommendation, so the project can move to a future AGPL version without
relicensing every contribution.

## Consequences

- Fits the positioning. "No hidden calls" and "read it in an afternoon" are
  promises about openness; the AGPL extends that promise to modified copies
  others run for you.
- Running, forking and changing edgar for yourself stays unrestricted.
- **Embedding.** A program that imports edgar through `edgar.run()` and is
  distributed or offered over a network is very likely a derivative work and
  inherits the AGPL. Plugin authors (providers, sandboxes, retrievers through entry
  points) should assume the same. Driving the `edgar` CLI as a separate process
  with `--json` or `--events` is the usual arm's-length boundary; the docs for
  EXT-9 and EXT-10 must say this plainly when they are written in M10.
- Some companies ban AGPL dependencies outright. That limits corporate adoption
  and embedding; it is the accepted cost.
- Dependencies must be AGPL-compatible. The five required dependencies (httpx,
  jsonschema, PyYAML, prompt_toolkit, rich) and the optional keyring are BSD, MIT
  or Apache 2.0, all compatible. A new dependency's licence is checked when it is
  proposed (NFR-5).
- Contributions come in under the same licence (inbound = outbound). No CLA.

## Rejected alternatives

**Apache 2.0** was the earlier default and is the better choice if the goal
becomes maximum adoption as a library embedded in closed products. What would change
the answer: the embedding API becoming the main way people use edgar, or a
company-backed maintainer needing permissive terms. Relicensing to something more
permissive later needs consent from every contributor, so it gets harder with each
merged pull request.

**MIT** gives up the patent grant for brevity, which is the wrong trade for a tool
that runs other people's code.
