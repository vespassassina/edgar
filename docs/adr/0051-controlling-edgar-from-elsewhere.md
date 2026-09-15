# ADR-0051 — Controlling edgar from elsewhere

**Status:** Accepted · 2026-09-14 · Constrains M10 (`edgar.run()`, EXT-9); amends
ADR-0048 decision 1; depends on PERM-15 as scheduled by ADR-0050

## Context

The maintainer wants to drive edgar from a phone: a harness running continuously
on a Proxmox container, an iOS app that opens projects, starts sessions, answers
permission prompts and uploads files, and the Mac terminal connected to the same
instance rather than running its own. Several containers at once, each subagent
with its own model and rules, is the same picture at a larger scale.

Every part of that collides with something edgar has said it will never be.
`ROADMAP.md`'s "Never" list carries **server, daemon or HTTP API**, **GUI**, and
**multi-user**; PRD §5.2 rejects a messaging gateway with the reason "needs a
long-running process", and rejects agent-to-agent protocols because "subagents are
function calls, not a network". Those entries exist so the question stops
recurring, and none of them is wrong.

The tension resolves once the layers are named. What the maintainer wants is not
edgar becoming a server. It is a *second program* that holds a human's attention
when the human is not at the keyboard, and embeds edgar the way any other program
would. edgar already owes that program exactly one thing — `edgar.run()` (EXT-9,
M10) — and one guarantee, the event and session formats frozen at 1.0 (EXT-10).

## Options and decisions

**1. Where the remote layer lives.** The alternatives are `edgar serve` as a
subcommand, an optional extra in the same distribution, and a separate project.
**Decided: a separate project, outside this repository and outside this budget.**
A daemon that owns sessions across projects, holds pending approvals, pushes
notifications and terminates TLS is several hundred lines of code that teach a
reader nothing about how an agent harness works. Inside `src/`, it would eat the
v1 budget and dilute the one claim the project makes — that you can read it in an
afternoon. Outside, it is a consumer of a frozen format like any other. The
"Never" list stands unamended: edgar ships no server, no GUI and no multi-user
model. Something else may.

**2. What the supervisor is allowed to be.** The tempting description is "it
emulates the local human". **Decided: it is a transport for a human and never a
stand-in.** It relays a prompt to whoever is holding the phone, or it blocks —
there is no third branch. A timeout that allows, a remembered "probably fine", a
convenience default: each would make an automated component widen policy, which
is the one thing PERM-6 forbids. A timeout may pause a turn. It may never answer
one.

**3. Where the loop runs when there are several containers.** Either edgar runs
in each container and they talk, or one edgar runs the loop and tool calls execute
inside containers. **Decided: the loop stays in one process; containers are a
Sandbox backend.** `shell.sandbox` already has `container` in its type (PERM-15),
moved to v2 by ADR-0050, and a subagent already runs the same loop with a
different config, a fresh transcript and a narrowed policy (ADR-0006), fanning out
concurrently (TOOL-12). Isolating a subagent's filesystem and network is therefore
a backend, not a new concept, and it keeps PRD §5.2's "subagents are function
calls, not a network" true. Two consequences follow: a container never justifies
a looser mode by itself — a human declares that in config, the harness never
infers it from "it's disposable" — and cost caps must aggregate across a fan-out,
or N agents means N independent daily caps.

**4. How a client follows a session.** A phone leaves the network constantly, so
a live socket loses events that a reconnect cannot recover. **Decided: clients read
from a cursor over the append-only record**, not from a live stream. The session
JSONL is already append-only and `replay()` already rebuilds what the user last
saw (ADR-0010, CTX-14); a sequence number per event and "give me everything after
N" makes a dropped connection a non-event. This is a requirement on the separate
project, recorded here because it is the decision that makes a mobile client
viable at all.

**5. One head, many clients.** The Mac terminal can either run its own edgar or
connect to the same instance as the phone. **Decided: both, and never ambiguously.**
`cli/repl.py` already separates the `Shell` that holds the logic from
prompt_toolkit, which drives the terminal, so a remote client is a different
transport for the same shell. But a connected terminal works in the container's
filesystem, not the local one: a session started on the Mac and approved from the
phone is only coherent because there is exactly one workspace. A client must
always make plain which instance and which workspace it is attached to.

**6. Uploads.** A project created from a phone starts empty and is filled by
upload: documents, images, whatever the work needs. **Decided: an upload is a file
in the workspace and attached context, never a learning source** (CLI-3, MEM-9).
It may be read by a tool and can never become a fact. An empty project also
disposes of the awkward case in project creation: there is nothing executable to
trust on day one, and `edgar trust` engages only once a control file exists,
which by then is one the human or the model just created.

**7. Signing in from a client.** ADR-0048 decision 1 put the OAuth redirect on a
loopback listener, on the assumption that the browser and the listener are on the
same machine. On a headless container they are not. **Decided: the client proxies
the sign-in** — it opens the authorization URL on the user's own device and hands
the returned code back to the supervisor, which passes it to the listener. The
alternative, binding the listener to a reachable address, would put an
authorization code on a network. Decision 1 of ADR-0048 is amended to "loopback,
or a code relayed by the client that opened the browser"; the promise that no host
edgar does not control ever sees the code is unchanged.

## Consequences

- edgar's obligations are `edgar.run()` (EXT-9) and the frozen formats (EXT-10).
  M10 should design `edgar.run()` with a supervisor as its first consumer:
  a caller that owns many sessions across many project directories, that starts
  turns nobody is watching, and that answers permission prompts out of band.
- Nothing in `src/` is added or changed by this ADR, and the "Never" list in
  `ROADMAP.md` is unchanged. A server, an HTTP API and a GUI remain things edgar
  does not ship.
- The `container` backend for `shell.sandbox` keeps its v2 slot (ADR-0050). When
  it is built, "one edgar, N isolated subagents" is a configuration, not a feature.
- Media input, which a phone client makes unavoidable, moves from "past v2" into
  v2 scope ([ADR-0052](0052-media-input-in-v2.md)).
- Open: whether the separate project is AGPL like edgar, and whether it depends on
  `edgar-harness` as a library or drives the CLI. The first matters more than it
  looks, because a network-facing AGPL program has obligations edgar's CLI does not.
