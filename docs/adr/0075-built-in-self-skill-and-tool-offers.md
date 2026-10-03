# ADR-0075 — edgar knows itself, and `init` offers git and web search

**Status:** Accepted · 2026-10-03 · Amends ADR-0023 and ADR-0057

## Context

Asked about itself, an edgar session guessed: its prompt says what a turn is, not
what edgar is, what its commands are or where its config lives. And out of the
box it had no search and no git, because both were only files under `examples/`.
The prompt is capped at 1,500 tokens with no volatile content (ADR-0023), so it
cannot carry a manual.

## Decision

- One built-in skill, `edgar` (`src/edgar/skills/builtin/edgar/SKILL.md`), found
  in every session at lowest priority: any scope of the same name replaces it.
  The prompt carries its one-line index and the body loads on demand, or when
  the typed words include "edgar". The prompt's cache prefix gains one fixed line.
- Its record is spelled out in `skills/discovery.py` (`SELF`), not parsed from the
  file, because parsing frontmatter imports PyYAML and a trivial run may not
  (NFR-1). A test checks the two agree.
- `edgar init` and `/init` offer two bundles from `templates/tools/`: git
  (default yes) and web search (default no, it needs a key). Answers copy the
  files into `.edgar/tools/`. Nothing is written when nobody is there to answer,
  and a file already there is never overwritten. Both still need `edgar trust`.
- The files under `templates/tools/` are copies of `examples/tools/`; a test
  checks they match.

## Consequences

- The `skill` tool and the `edgar` index line are present in every session. That
  costs a few hundred prompt tokens per request, once, in the cached prefix.
- The skill body must be kept true by hand. The tour stop and this ADR are the
  reminder; the "What edgar does not do" section is the one most likely to rot.
- web search stays off until the user picks a host and sets a key, so no host is
  chosen for them (PRV-15).
