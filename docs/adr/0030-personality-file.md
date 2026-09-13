# ADR-0030 — A personality file for tone and style, owned by the user

**Status:** Accepted · 2026-09-13 · Complements ADR-0023 (the shipped prompt carries no style opinions)

## Context

ADR-0023 keeps the shipped system prompt short and free of style opinions: it
describes the harness, the tools and the safety rules, nothing about how edgar
should sound. People still want a say in that: terse or chatty, formal or casual,
which language to answer in, whether to explain or just act.

`AGENTS.md` is the wrong place for this. It holds instructions about a project and
is shared with everyone who works on it, and with other agents that read the same
file. Tone is personal and follows the user from project to project.

## Decision

A **personality file** in plain Markdown:

| Location | Scope |
|---|---|
| `~/.edgar/personality.md` | the user, every project |
| `.edgar/personality.md` | this project; **replaces** the user file when present |

- **Placement.** It is added to the prompt right after the system prompt, above the
  cache breakpoint, and read once at session start (CFG-8). It never changes within
  a session, so the cached prefix stays byte-stable (CTX-17).
- **Visibility.** `edgar prompt show` prints it after the system prompt, with its
  source and token count. `/status` names the file in use.
- **Size.** It counts toward the prompt, so a file over 500 tokens gets a warning
  in `edgar prompt show` and `edgar doctor`. It is not refused: it is the user's
  prompt to spend.
- **Ownership.** It is a control file (PERM-12): the model's `write` and `edit` on
  it always ask, the learner never writes it, and the controller may only propose a
  diff. Only a human widens what edgar is told about itself.
- **No shipped personality.** edgar ships no default file, so with no file present
  the prompt is exactly the shipped system prompt.
- **Precedence.** It shapes tone and style only. The system prompt's safety rules
  and the permission engine are unaffected by anything the file says; the file is
  placed after the system prompt and introduced as user preferences.

## Consequences

- One more control file in the PERM-12 set and one more section in the assembled
  prompt (CTX-1, CTX-19).
- A personality file cannot grant anything. A file that says "never ask for
  permission" changes nothing, because permissions are decided by `decide()`, not
  by the model's willingness.
- Project replaces user, not merges: two files merged in unknown order produce
  contradictions nobody can debug.

## Rejected alternatives

**Style in the shipped prompt.** Every user pays for opinions they did not choose,
and changing them means editing a file edgar owns.

**Style in `AGENTS.md`.** Mixes personal preference into shared project
instructions, and other agents reading the file inherit it.

**Merging user and project files.** What would change the answer: evidence that
people want a user baseline plus small project tweaks often enough to justify
defining merge rules.
