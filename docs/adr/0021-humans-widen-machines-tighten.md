# ADR-0021 — Humans widen, machines tighten: taint, control files and project trust

**Status:** Accepted · 2026-09-13 · Amends ADR-0004 and PRD §9.5

## Context

"Policy may only tighten" (PERM-8, CTRL-8) is the right invariant, but v0.2 stated
it about subagents and the controller and left four side doors open.

1. **The agent could edit its own config.** In `auto` mode, `write` and `edit` are
   allowed inside the working directory, and `.edgar/config.toml` is inside the
   working directory. The model could add a `shell_allow` rule and widen its policy
   for the next session.
2. **"Always allow" wrote to config.** PERM-6 persisted interactive grants into
   `config.toml`, which CFG-7, MEM-2 and §9.5 all say machines never write.
   `schedule_self` also needed to write somewhere, and `schedules.toml` is listed as
   hand-authored.
3. **Auto mode and untrusted content.** With `fetch` or an MCP tool in play, `auto`
   mode combines private data, untrusted instructions and a way out (shell and
   network). A fetched page can tell the model to `curl` a file somewhere.
4. **A cloned repository is executable.** Project config can declare hooks, MCP
   servers, command tools, extensions and `verify.command`. All of them run on
   launch or at turn end, and in `auto` mode none of them prompt.

Shell deny patterns do not close any of these. They are glob matches over a string,
and `sh -c`, `find -delete` or a second command after `;` gets past them.

## Options

**A. Document the risks** and leave the mechanism as is.

**B. A sandbox** (containers, seccomp, Windows AppContainer). The only real
boundary for untrusted work, and far outside the size and platform budget.

**C. Close each door with a small rule** in the pure `decide()` function and the
config loader, and state plainly what remains.

## Decision

Option C, under one restated invariant:

> **No automated component (model, tool, subagent, controller, learner, hook) may
> widen policy. Only a human action widens it: editing a config file, answering a
> prompt, passing a flag, or running `edgar trust`.** [PERM-8, CTRL-8]

**1. Control files.** The following are control files: the configured instruction
files (default `AGENTS.md`), `.edgar/config.toml`, `~/.edgar/config.toml`,
`schedules.toml`, and everything under `.edgar/{agents,tools,extensions}/` and
`.edgar/skills/` except `learned/`, plus the user-scope equivalents. For `write`
and `edit` they are **Ask in every mode except `yolo`**, and denied when
non-interactive, in the hard layer of `decide()` that rules cannot override.
Config and instruction files are **read once at session start** [CFG-8], so even
an approved edit takes effect next session, and the REPL says so.

The shell can still write them. As a detector rather than a boundary, edgar stores
a hash of the control files at session end and warns at the next start if they
changed while a session was running [PERM-12].

**2. Machine-owned state lives in the DB.** Interactive "always" grants go to a
`grants` table in the project's `edgar.db`, listed by `edgar permissions list`,
removed by `edgar permissions revoke ID`, and shown with origin `grant` in `config
show --resolved` [PERM-6]. `schedule_self` writes to a `self_schedules` table
[SCH-11]. Human-invoked writers (`edgar init`, `edgar schedule add`) create or
append from templates and never rewrite existing content.

**3. Taint.** `decide()` gains one input, `tainted: bool`. The session becomes
tainted when a result from a network-sourced tool (`fetch`, HTTP tools, MCP tools)
enters the transcript, and stays tainted for the rest of the session. The status
line shows it. While tainted, **in `auto` mode only**, the mode default for `shell`,
command tools not marked `read_only`, and network-egress tools becomes Ask (denied
when non-interactive). Explicit per-tool rules and grants still apply, because
they are human decisions. `read-only`, `ask` and `yolo` are unchanged [PERM-11].

**4. Project trust.** Executable project config means project-scope hooks, MCP
servers, command and HTTP tools, extensions and `verify.command`. On first use in
an interactive session, edgar lists them and asks whether to trust the project.
Trust is stored in the user-scope DB, keyed by project path and a hash of the
executable config, and is asked again when that hash changes. A non-interactive
run in an untrusted project that has executable config **exits 3** with a hint to
run `edgar trust` or pass `--no-project-exec`. User-scope config is trusted by
definition [PERM-13, CLI-19].

**5. Shell matching, honestly.** Commands are split on `;`, `&&`, `||`, `|` and
newlines after whitespace normalisation. A command is denied if any segment matches
a deny pattern and auto-allowed only if every segment matches an allow pattern.
Command substitution (`$(…)`, backticks) is never auto-allowed. The docs call this
what it is: a speed bump. The boundaries are the mode, the Ask prompt, taint,
and running untrusted work inside a container or VM [PERM-14].

## Consequences

- **The invariant is checkable.** Property tests assert that no generated sequence
  of automated actions produces a policy wider than the one the session started
  with, that `decide()` never returns Allow for a control-file write outside `yolo`
  or an interactive prompt, and that tainted `auto` never allows shell by mode
  default
- **`auto` gets less convenient after a `fetch`.** Users who want both add explicit
  rules for the commands they trust. That friction is the point
- **Cloning a repo and running edgar is safe by default**, which it was not
- **`decide()` stays pure.** Taint and control-file status are inputs, computed by
  the caller
- **What remains** is listed in BLUEPRINT §7.4 (residual risks): file contents in the repository
  are not a taint source, so a malicious README can still influence the model; the
  shell can do anything the user can; and `yolo` is exactly what it says

## Rejected alternatives

**A (document only)** is rejected because doors 1, 2 and 4 are cheap to close and
expensive to explain after an incident.

**B (sandbox)** is rejected for Core and v1 on size and platform parity. Running
edgar inside a devcontainer is documented as the recommended setup for untrusted
work. Revisit if a portable, dependency-free sandbox appears.

**Per-turn taint** (clearing when the tainted result is compacted away) was
considered. It is harder to explain and easy to get wrong, because a summary can
carry the injected text forward. Sticky-per-session is the simple answer (OQ-7).
