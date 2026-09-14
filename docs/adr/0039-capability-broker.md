# ADR-0039 — Add a capability broker in v2: every tool call checked against what the human asked for

**Status:** Accepted · 2026-09-14 · Extends ADR-0021 (humans widen, machines tighten); adds milestone M17 to v2

## Context

The permission engine answers "may this session use this tool on this path?" The
answer is fixed by mode, rules, grants and taint, so it cannot tell the file you
asked about from the one next to it. If you type "summarise `reports/q3.md`" and the
report contains a line telling the agent to read `reports/2024-salaries.md` and post
it somewhere, every check passes: the path is inside the working directory and
`auto` allows reads. Taint (PERM-11) tightens shell and network after untrusted
content arrives, but it narrows by tool kind, never by task. An agent is the classic
confused deputy. It really is who it says it is, so identity and role checks cannot
catch it.

The maintainer prototyped an answer on 2026-09-02: a standalone capability broker in
about 1,050 lines of standard-library Python, thirty tests with one per invariant, and
an executable confused-deputy example. It has three ideas:

- **Intent, the why.** What a human asked for, recorded before anything acts.
- **Capability, the may.** Authority bound to that intent, which only narrows as it
  is delegated.
- **Provenance, the did.** A signed hash chain linking every decision, refusals
  included, back to the why.

It also separates two layers:

- **The ceiling:** what a tool could ever do. Hard-coded, static and small.
- **The ticket:** what this request may do. Minted per ask.

Effective authority is their intersection. edgar already has the ceiling: tool
definitions (command tools' argv templates, HTTP tools' fixed host), the permission
engine's hard layer, and the sandbox. It has no ticket.

What makes the design non-obvious here:

- **The prefix is fixed for a session.** The prototype hands the model tools with
  the resource already closed over, so a handle for `reports/q3.md` has no path
  argument for injected text to fill. In edgar, tool schemas sit above the cache
  breakpoint and are fixed for the session (CTX-1, CTX-17), so tools cannot be
  rebuilt for each task.
- **Machines must not author authority.** If the model wrote the caveats from the
  prompt, the model would be issuing its own ticket.
- **Most of the prototype's next steps are on edgar's Never list:** the daemon, a
  wire protocol, and the multi-tenant service.

## Options

**A. Taint and permissions only (status quo).** Nothing new to read. Stops shell
and network after untrusted content in `auto`, but not a read inside the working
directory that the task never needed, and keeps no record tying an action to the
request it served.

**B. Bound handles, as in the prototype.** The strongest form: there is no argument
to inject. It needs a tool list per task, which breaks the byte-stable prefix, the
provider's cache and CTX-17. It also only works when the targets are known up
front, and the prototype's notes say exploration needs a handle-request path that
was never built.

**C. A ticket checked in the tool pipeline.** The tools and schemas stay as they
are. Each call's arguments are resolved as the permission engine already resolves
them, and are checked against the ticket of the intent they serve. This is as
strong as B as long as the pipeline is the only way to reach a tool. In edgar it
is: every call from every source goes through `tools/execute.py` (§6.2). That also
closes the gap the prototype named, "an agent that never calls the broker is
unconstrained".

**D. A policy language** (Biscuit-style Datalog, Macaroons or UCAN). More
expressive and interoperable, but a dependency (NFR-5), and a mechanism the reader
has to learn before they can read the check.

## Decision

**C, as a v2 package `edgar.broker`, in a new milestone M17.** The broker adds no
model call, no network and no process. Its decision is a pure function beside
`decide()`, and it can only refuse.

**Intent.** An intent is recorded only from text a human typed: a REPL line (typed
or queued), the `-p` argument, or a hand-authored `schedules.toml` entry. That is the same source MEM-8 trusts for facts, and it is edgar's answer to
the prototype's open question 4, "what if the intent itself was injected?" An intent
never comes from tool output, fetched content, piped stdin, `@file` attachments or
model text. Some things only refine an existing intent and never start a new root:
- a subagent's task description, which the model wrote;
- a `schedule_self` entry;
- a `/steer`, which refines the turn it steers.

The why stays the same all the way down a chain.

**Ticket.** One per intent, carrying `intent_id` as a field rather than as a
caveat. That settles the prototype's open question 1: the check that a request
names its ticket's intent is an invariant, not a policy.

Five caveats, deliberately small:

| Caveat | Narrows to | Example |
|---|---|---|
| `tools` | these tool names | `tools=read,grep,edit` |
| `paths` | resolved paths under these globs, for any tool that takes a path | `paths=reports/q3.md` |
| `hosts` | these hosts for `fetch`, HTTP tools and remote MCP | `hosts=api.github.com` |
| `calls` | at most N tool calls under this intent | `calls=20` |
| `until` | a wall-clock expiry | `until=10m` |

A ticket with a `paths` or `hosts` caveat refuses `shell`, and command tools not
marked `read_only`, unless `tools` names them explicitly. What a shell touches
cannot be checked against a path, so allowing the shell has to be a visible,
deliberate choice.

**Caveats come only from people, or narrow what people gave:**
1. `--scope KEY=VALUE` on `-p` (repeatable). In the REPL, `/scope KEY=VALUE`
   (repeatable), `/scope` alone to show the current ticket, and `/scope clear`.
   The REPL's scope seeds the ticket of every prompt that follows.
2. A `scope = { … }` table on a `schedules.toml` entry.
3. Delegation: the `task` tool attenuates the parent's ticket with the agent
   definition's `tools`, plus an optional `scope` argument. The model may pass
   that argument because it can only add caveats. The child's subject is the
   subagent (`task:explorer#2`), so a leaked ticket cannot be spent by another
   agent.
4. The controller's `tighten_policy` adds caveats to the live ticket (CTRL-8).

With no scope given, the ticket has no caveats. The broker then refuses nothing
the permission engine allows, and only keeps the receipt.

**Where it sits.** It is a veto in the `pre_tool` stage that M10 builds for hooks
(EXT-6). That stage takes a list of in-process veto callables, filled by
`cli/main.py` through `importlib` the way the post-turn gate is, so Core and v1
never import the broker (NFR-12). A veto callable can return a refusal or nothing,
never an allow, so "machines tighten" holds by type.

A refusal is a `ToolResultBlock(is_error=True)` whose `ErrorRecord` has kind
`out_of_scope` and names the caveat that refused. The model sees it like any other
denial (invariant 4). The REPL prints a notice naming `/scope`.

Widening a ticket is a human action: `/scope` in the REPL, or a new `--scope`.
There is no prompt in the middle of a call. A non-interactive refusal stays a tool
error and does not change the exit code.

**Receipt.** `.edgar/sessions/<id>/receipt.jsonl` (`runs/<id>/` for a scheduled
run) is append-only. Each line carries
the SHA-256 of the previous line and an HMAC-SHA256 signature. Entry kinds:
- `intent`, quoting the typed text;
- `ticket`;
- `delegate`;
- `allow` and `refuse`, with the caveat that refused;
- `permission`, the engine's decision for the same call, taken from the bus.

Refusals carry the same weight as allows: a record of what an agent tried on your
behalf and was refused is the part nobody else keeps. Use counts are rebuilt from
the receipt on `--resume`; nothing important lives only in memory.

The key is `~/.edgar/receipt.key`: 32 random bytes, created on first use,
readable by the user only, and added to the hard layer's credential paths so the
agent's own tools cannot read it.

`edgar receipt [ID] [--refused] [--verify]` prints the story intent by intent.
`--verify` checks the chain and the signatures and exits 1 at the first break.

**Scheduling.** A scheduled run's intent has the actor `schedule:NAME`, and the
entry's `scope` and per-entry allowlist (SCH-8) as caveats. A `schedule_self`
entry carries the ticket of the session that created it, attenuated. A run the
agent scheduled for itself can never hold more authority than the run that
scheduled it.

**Config.** `[broker] enabled`, on by default once v2 is installed, like
`memory.autolearn`. With no scope it only writes the receipt. `edgar doctor`
reports it.

**Size.** The estimate is about 400 lines: caveats, the ticket and chain check,
`authorize()`, the receipt, and the veto. The prototype's 1,050 lines include its
own tool registry, request type and path handling, all of which edgar already has.
It counts against v2's 11,000. If v2 runs over, something moves past v2; the
budget does not move.

## Consequences

- **Load-bearing: the tool pipeline is the only way to a tool.** Option C is as
  strong as bound handles only while nothing reaches a tool around
  `tools/execute.py`. A new tool source or a shortcut past the pipeline silently
  turns the broker into an advisory check. An integration test calls every tool
  source with a refusing ticket.
- **Load-bearing: intents come from typed text only.** Anything that mints an
  intent from other text reopens the injected-intent hole. It shares its source
  with MEM-8 and is tested the same way, by what the function accepts.
- **Load-bearing: caveats only accumulate.** A child is verified to carry every
  caveat of its parent, structurally, not by trusting whoever built it. A property
  test generates delegation chains with dropped caveats and asserts that none
  verifies.
- The receipt is tamper-evident against the agent, which cannot read the key, and
  against accidental edits. It is not tamper-evident against the user or another
  process running as the user, because HMAC is symmetric. That is honest for one
  person on one machine, which is who edgar is for (PRD §3). It is not an
  enterprise audit trail and does not claim to be.
- The receipt duplicates some of what `PermissionResolved` events already put in
  the session JSONL (PERM-10). The JSONL stays the record of the conversation. The
  receipt is the record of authority, signed and keyed by intent, and it can be
  read without the conversation.
- A scoped ticket can refuse something the task genuinely needed. The model sees
  which caveat refused, and the human widens with `/scope`. That cost is the point:
  the widening is visible and typed by a person.
- A shell allowed by a ticket can do anything the shell can. The residual risks in
  BLUEPRINT §7.4 still apply; the broker narrows everything except the shell.
- The pipeline gains one stage from v2 on. With no scope set, the cost is one
  small JSON line per call, written after the call's decision.

## Rejected alternatives

- **Bound handles (B).** Revisit if providers stop caching prefixes, or if edgar
  ever builds tool lists per turn for another reason. Then welding the resource
  into the handle is strictly stronger and the per-call check becomes a backstop.
- **A model deriving the scope from the typed prompt.** It is tempting, because
  few people will type `--scope`. But the model would be writing its own
  authority, and an extraction step is model judgement on the authorisation path.
  Revisit as a controller proposal the human confirms, if receipts show that
  unscoped sessions are the norm.
- **A policy language (D).** Revisit if the five caveats prove too coarse on real
  tasks; the seam is the caveat check.
- **Ed25519 signatures.** They need a dependency, and in one process they buy
  nothing HMAC does not. Revisit if a receipt ever has to be verified by someone
  who must not be able to mint.
- **A local broker daemon or a service** (the prototype's next steps). Both are on
  the Never list: no daemon, no multi-user (PRD §5.2). The broker is a library
  inside one edgar process and stays one.
- **Agent identities (SPIFFE or similar).** Subjects are edgar's own agent ids. An
  attested identity matters across machines, which edgar does not span.
- **A prompt in the middle of a call when a ticket refuses.** It is friendlier,
  but it makes the veto an ask and doubles the prompts per call. Revisit if
  `/scope` turns out to be too slow a way to widen in practice.
