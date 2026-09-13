# ADR-0033 — The REPL before the safety milestone, and CLI and API tools with it

**Status:** Accepted · 2026-09-13 · Reorders ROADMAP M3 and M4; moves custom tools and trust from M6 to M3; amends CLI-29

## Context

After M2, edgar runs against real models but only one prompt at a time. The
maintainer asked for three things soon: an interactive shell, a way to pick and
configure models from edgar itself, and tools built on a CLI or an HTTP API
rather than MCP. An MCP server's tool schemas cost around 3,000 tokens on every
request; a command tool or an HTTP tool costs a few dozen.

The roadmap had tools and permissions (M3) before the REPL (M4), and custom
command and HTTP tools in M6.

## Options

**A. REPL next, then M3 with custom tools.** The REPL is safe to ship now,
because the only tools are `read` and `ls`, confined to the working directory.
The permission prompts M3 needs (`ask` mode) have nowhere to appear without a
REPL anyway. Custom tools run programs and reach hosts, so they belong with the
permission engine and project trust, in M3.

**B. Keep M3 first, with custom tools moved in.** The safety boundary lands
first, and the REPL waits one milestone.

**C. REPL, then custom tools with a minimal permission check.** Fastest to a
useful tool, but the full permission engine and verify gate would lag behind
tools that run programs.

## Decision

**A.** Chosen by the maintainer on 2026-09-13. Milestone IDs keep their numbers,
so references stay valid. The order of work becomes:

**M0, M1, M2, M4, M3, M5, M6**, then v1 as before.

- **M4 next**: the REPL, streams and status line, plus the model picker
  (ADR-0034, CLI-30). Items that depend on later milestones show as unavailable
  until then (for example taint and trust in `/status`).
- **M3 gains** command tools and HTTP tools [TOOL-6], and project trust with
  `edgar trust` and `--no-project-exec` [PERM-13, CLI-19], all moved from M6.
  Trust must ship with them, since a cloned repo's `.edgar/config.toml` may
  declare a command tool.
- **`/browser` has a CLI form** [CLI-29]. `[browser]` names either a command
  tool (a browser CLI, at the cost of its schema) or an MCP server. The CLI form
  lands in M3 with command tools; the MCP form stays in M8.
- **M6 keeps** skills, examples, the first docs, `edgar login` (ADR-0032) and
  the Core release.

## Consequences

- The Core budget is unchanged. The items only move.
- M4's done criteria no longer mention permission prompts. M3's now include the
  custom-tool criteria from M6: an argument containing `; rm -rf ~` reaches the
  program as one argv element, an HTTP tool cannot be pointed at another host,
  and a token never appears in the transcript, events or logs.
- MCP stays the right tool for a server that is only available as MCP. Deferred
  schemas (TOOL-15, M8) are what keep it affordable when it is used.
