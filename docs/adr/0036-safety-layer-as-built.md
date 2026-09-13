# ADR-0036 — The safety layer as built: one pure decision, a guard around it, and what moved

**Status:** Accepted · 2026-09-13 · Refines ADR-0004, ADR-0021 and BLUEPRINT §4.2, §7; lands in M3

## Context

M3 built the permission engine, the remaining built-ins, the verify gate, command
and HTTP tools, and project trust. The Blueprint sketched `decide()` with eight
parameters and left several questions open: what "outside the working
directory" does now that writes exist, how an Ask resolves with nobody present,
where the audit log lives before sessions reach disk, and how yolo is reached.
The size budget was also tight: M3 began with 1,647 Core lines left for M3, M5
and M6.

## Decision

- **`decide(tool, subject, policy)`, pure.** A frozen `Policy` carries mode,
  paths, rules, grants, taint, interactivity and a control-file predicate. The
  caller (`permissions/guard.py`) resolves the `Subject` (a fully resolved path,
  a command line, or a URL), builds the policy per call, asks when the answer is
  Ask, remembers "session" and "always", and emits `PermissionResolved`.
  Command and HTTP tools supply their own subject: the rendered argv, or the URL
  with arguments filled in and `${env:…}` left unresolved.
- **Outside the working directory is Ask, not deny**, for reads and writes alike,
  and part of the hard layer: no rule can allow it, only a human's grant for
  that exact path. Credentials (`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.kube`,
  `~/.docker`, `~/.netrc`, `~/.config/gcloud`) are denied outside yolo. A short
  list of catastrophic commands (`rm -rf /`, `rm -rf ~`, `mkfs*`, a fork bomb) is
  denied even in yolo.
- **Nobody to ask means no.** Non-interactive, every Ask becomes a Deny marked
  `needed_prompt`. The call's error goes back to the model, as every tool failure
  does, and `-p` exits 5 at the end with the result still on stdout (PERM-7).
- **Grants are exact** (tool, subject) pairs. "Always" writes one to the
  project's `.edgar/edgar.db` and never to config; a control-file answer is never
  stored, so a control file asks every session.
- **yolo needs `EDGAR_YOLO=1`, or `--mode yolo` (or `/mode yolo`) and the word
  typed.** A config file or `EDGAR_PERMISSIONS_MODE` alone is an error (PERM-9).
- **The audit trail is the event stream.** Every decision, allows included,
  emits `PermissionResolved(tool, subject, decision, source, reason)` (PERM-10),
  visible under `--events`. The file copy comes with the session JSONL in M5.
- **Processes die as a group.** `shell`, command tools and the verify command
  start in their own process group (a new session on POSIX, a new process group
  on Windows) and are killed as a group on cancel or timeout.
- **The verify command is authorised before the turn** through the same guard,
  as a `shell` call; a `verify.command` from project config also needs trust.
- **`grep` is Python's `re` over the files**, not ripgrep: no dependency and no
  program to find, at the cost of speed on very large trees.

## What moved

- **`/browser` (its CLI form) moves to M8**, next to its MCP form. With command
  tools in place, a browser CLI can already be declared as an ordinary tool in
  `.edgar/tools/`, which is most of the value.
- **The control-file hash warning moves to M5**, which has a session end to store
  the hash at.

## Consequences

- `permissions/` is at 100% branch coverage over the suite, and the mode table
  is tested cell by cell.
- The loop is at 182 of its 200 lines. What M5 adds to it (the budget check,
  compaction) has to come in as collaborators.
- **Core is at 4,415 of 5,000 lines after M3.** 585 lines are not enough for M5
  and M6 as specified, so by the roadmap's own rule something moves to v1 before
  M5 starts. That choice goes to the maintainer.
