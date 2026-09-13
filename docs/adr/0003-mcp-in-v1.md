# ADR-0003 — MCP client in v1, four tool sources, no server mode

**Status:** Accepted · 2026-09-02

## Context

The harness needs extensibility both at code time and at runtime. MCP is the
de-facto tool interop standard by 2026, and for a project meant to be a base others
build on, ecosystem access is close to table stakes.

The useful separation: **supporting MCP** and **being shaped by MCP** are different
costs. A contract designed MCP-shaped makes a later client a small adapter. A
Python-native contract, say a decorator over typed args returning Python values,
makes retrofitting MCP a rewrite of the contract and everything built on it.

## Options

**A. MCP-shaped contract now, client later.** Cheap, defers the subprocess
lifecycle, JSON-RPC framing, transport and discovery work.

**B. MCP client in v1.** More upfront work, but the contract gets validated against
a real second tool source immediately rather than discovering three milestones later
that it was subtly wrong.

**C. Skip MCP.** Simplest and most readable, isolates the project from the ecosystem.

## Decision

Option B, plus an explicit decision on the full set of extension surfaces.

**Four tool and extension sources:**

1. **Built-in tools** — Python, shipped with the harness
2. **Custom tools** — declared in TOML or markdown, shell out to a command, no
   Python required
3. **MCP servers** — stdio and HTTP/SSE transports, in v1
4. **Skills** — Claude-compatible `SKILL.md` format

No MCP **server** mode, now or later. It is a different product, consumes
attention, and teaches nothing the client does not.

## Consequences

**Tool contract is MCP-shaped by construction:** name, description, JSON Schema
input, content-block output, async, namespaced. The MCP client becomes translation,
not a parallel system.

**Custom shell-out tools are the highest value per line of code** in the whole
project for the tinkerer audience, and cost almost nothing once the contract is right.

**Skills are not tools.** They are prompt-level extensions, which needs:
- A `skill` tool that loads the body on demand
- A discovery pass reading **frontmatter only**, so name and description sit in
  context while the body does not (progressive disclosure)
- Three search paths — bundled, user, project — with project winning collisions

**Per-skill `HISTORY.md`** in the skill folder doubles as scoped durable notes. One
mechanism serving both the skill-memory need and the general history need, rather
than two systems.

**MCP servers spawn lazily on first use** [TOOL-8]. A project with five configured
servers would otherwise pay five process launches on every invocation and destroy
the startup budget from ADR-0001.

**Namespacing and collision order** must be deterministic and warned about at
startup: `project custom > user custom > MCP > builtin`, namespaced as
`mcp__server__tool`.

## Rejected alternatives

**Deferring the client** was the initial recommendation and remains defensible.
Overridden because validating the contract against a real second source early is
worth more than the deferred effort, and because MCP-in-v1 makes the project
immediately useful rather than immediately interesting.

**Skipping MCP** was rejected: it would make edgar a nice thing to read and a
tedious thing to use.
