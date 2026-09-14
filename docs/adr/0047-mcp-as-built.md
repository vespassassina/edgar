# ADR-0047 — MCP as built

**Status:** Accepted · 2026-09-14 · Implements the first half of M8; refines
ADR-0021, ADR-0029 and ADR-0036

## Context

M8 adds MCP servers as a tool source: stdio and Streamable HTTP, namespacing,
untrusted results, deferred schemas, project trust, `edgar mcp list|test` and
`/browser` [TOOL-7, TOOL-8, TOOL-9, TOOL-13, TOOL-15, PERM-13, CLI-29]. It cost
617 lines of code; `src/` is at 6,419 of v1's 8,000. OAuth for remote servers and
`edgar login` [ADR-0032, PRV-18] are the second half and are not built yet.

The tension the milestone turns on: TOOL-8 says nothing is started until a tool is
called, and the model cannot call a tool whose name it has never seen. Every
decision below follows from resolving that without starting five processes at
session start.

## Options and decisions

**1. How a server is configured.** The Blueprint sketched an array of tables,
`[[mcp.servers]]` with a `name` key. **Decided: `[mcp.NAME]` tables instead.** The
config loader already merges layered files key by key and records where each key
came from; an array of tables would replace wholesale, so a project could not add
a server without repeating the user's. `[mcp.NAME]` reuses `[providers.NAME]`'s
machinery exactly, and a project overriding one key of a user's server is then a
normal, traceable merge. Each block takes either `command` (with `args`, `env`) or
`url` (with `headers`), never both and never neither; `timeout_s` defaults to 60.
`[browser]` is a plain section with `tool`, or `command` and `args`.

**2. How a session knows a server's tools without starting it.** (A) Start every
server at session start and ask. (B) Ship no tools until the model asks for them.
(C) Cache each server's tool list and build the proxies from the cache.
**Decided: C, with B for what is not cached.** `mcp_tools` in `~/.edgar/edgar.db`
keys the list by a sha256 of the server's name and its whole config block, so a
changed block is a new key and a stale list can never be served. A session builds
its MCP tools from the cache and starts nothing; the first call starts the server.
A server no session has run yet has nothing cached: `tool_search` names it in its
description and starts it when the model looks for something, and `edgar mcp list`
starts every one of them. The cost is that a server that changed its tools between
sessions is one call behind; `tools/list_changed` notifications and `edgar mcp
list` both refresh it, and the call itself fails loudly if the tool is gone.

**3. Where deferred tools are listed.** TOOL-15 says the deferred names stay in
the prompt with one line each. (A) A section the prompt builder adds. (B) The
description of `tool_search` itself. **Decided: B.** The listing then travels with
the tool that acts on it, costs nothing when nothing is deferred, and no prompt
builder learns about MCP. `ToolRegistry(tools, budget)` defers every `kind ==
"mcp"` tool when the schemas together pass `tools.schema_budget` (4,000 tokens by
default; the eight built-ins cost 725), and `tool_search`'s description is built
fresh on each request from what is still deferred, trimmed to the room the budget
leaves. A deferred tool is not hidden: called by name, it runs. This is a way of
spending the schema budget, not a permission boundary.

**4. What an MCP tool is allowed to be.** Its category is `shell` for a local
program, which runs with your rights, and `network` for a URL; its output is
always `untrusted_output`, so a result taints the session and tightens what comes
after [PERM-11]. What a server claims about its own tools (`readOnlyHint`,
`destructiveHint`) is printed by `edgar mcp list` for a human to judge and is
never read by `decide()` [TOOL-13]: a server cannot talk its way into being
allowed. A call's permission subject is the tool name and a 120-character preview
of its arguments, and edgar reads no path out of them, because the server decides
what its arguments mean.

**5. Collision order.** Builtins, then extra tools (memory, skill), then MCP, then
the user's `[tools.NAME]`, then the project's: later wins and a warning names what
was replaced [TOOL-9]. A project's MCP server, like its command and HTTP tools,
needs `edgar trust` before it is offered at all [PERM-13].

**6. Which transports.** Streamable HTTP only, not the deprecated two-endpoint
HTTP+SSE: one way in is enough and the spec's current one is it. Protocol
`2025-06-18`; the stdio transport answers a server's `ping` and refuses every
other server-initiated method; the HTTP transport accepts a JSON or an SSE answer,
keeps `Mcp-Session-Id` and sends `MCP-Protocol-Version` after the handshake.
`${env:NAME}` in `env`, `url` and `headers` is expanded at spawn time through the
same `expand()` the HTTP tools use, which registers the value for redaction, and
every result and error is scrubbed.

**7. What `/browser` does.** Nothing on its own [PRV-15, ADR-0036]. With
`[browser] tool = "..."` it says whether that tool is ready; with `[browser]
command = ...` it starts that MCP server, adds its tools to the session and stops
it when the session ends; with no `[browser]` block it prints the two blocks you
could write. It never picks a browser for you and never installs one.

## Consequences

A session with five servers configured costs what a session with none costs, and
an e2e test proves no process starts. Forty MCP tools cost the schema budget and
no more. Against that: the first call to a cold server pays its start-up, the tool
cache is one more piece of state that can be stale, and `tool_search` adds a round
trip when the model needs a deferred tool it has not loaded. All three are visible
to the user: `edgar mcp list` starts and refreshes everything, `edgar mcp test
NAME` is one server end to end, and both print where each server came from.
