# ADR-0070 — The setup wizard's questions and the vendor list are data files

**Status:** Accepted · 2026-10-02 · Extends ADR-0034

## Context

`edgar init` asked one question (the model) and the picker listed only the six
built-in providers. The maintainer asked for more settings in the wizard and the
whole vendor list in the providers. Core and v1 are at their line budget
(9,512 of 9,500 before this change), so each new question and vendor written as
Python would be debt.

## Decision

Both lists are TOML under `templates/`, which counts for nothing against the
line budget (ADR-0040), like `config.toml` and the prompts.

- `wizard.toml`: each question's text, the commented line in `config.toml` it
  replaces, its key, and what it accepts (`text`, `money`, or listed words). An
  answer replaces the comment; Enter leaves it. yolo is not in the list
  (PERM-9). Nothing the wizard writes is a secret (CFG-6).
- `providers.toml`: sixteen vendors with an OpenAI-compatible endpoint, each
  a host and a key variable, or no variable for a server on your own machine.
  The picker lists them after the built-ins. Choosing one writes its
  `[providers.NAME]` block into the new config. No `Quirks` row is added, so
  nothing is routed to a vendor the user did not pick (PRV-15, no hidden
  behaviour). A vendor with no key set takes a typed model name and tells you
  which variable to export.

## Consequences

- The code added is about 43 lines of code: the reader, the block writer, the
  picker merge and the REPL reload. That leaves the non-removable budget at
  9,555 of 9,500, 55 over. The maintainer accepted the overage on 2026-10-02,
  as with ADR-0069. The test `src/ without removable packages` stays red until
  lines are freed or the budget is revisited.
- A vendor's host can change without a code release. Hosts and key variables
  are the vendors' documented ones as of this date and have not been called
  from here; a wrong one fails at the first request with the provider's error.
- An existing `config.toml` is never edited (ADR-0034). If one exists, the
  wizard asks nothing it could not apply and prints no block; add
  `[providers.NAME]` by hand.

## Rejected

- One `Quirks` row per vendor in `quirks.py`: about a line per field, and each
  row is a default host that is not the user's choice.
- A removable module for the wizard: it is Core's first-run path, and the seam
  would only move the lines out of sight (ADR-0069 did that once already).
