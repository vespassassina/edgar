# ADR-0031 — The provider layer as built: what the sketch left open

**Status:** Accepted · 2026-09-13 · Refines ADR-0002, ADR-0009 and ADR-0020; resolves OQ-3

## Context

BLUEPRINT §5 sketched the provider layer before any of it existed: a quirks table
with a `"per-model"` tool-support value probed on first use, reasoning replayed to
the same family, cassettes recorded from live APIs, a pricing table. Building M2
turned each sketch into a decision, and several came out differently from how the
sketch read. They are recorded here so the next person does not re-derive them.

## Decision

**Tool support is learned from the first refusal, not probed.** No adapter sends
an extra request to find out what a model can do. Tools go out with the first
request; a server that rejects them (Ollama says "does not support tools") becomes
a `ProviderError` whose hint names `native_tools = false`. That setting switches
the server to text tool calls: the tool list travels in the system message on the
wire, and calls come back as JSON parsed by `repair.py`. The quirks field is a
plain `bool`, and the `"per-model"` value is gone. It still meets PRV-10 (explicit
degradation) and PRV-12 (probed on first use): the first use is the probe.

**Chat Completions never replays reasoning.** The API has no standard field for
sending reasoning back, and servers disagree about the non-standard ones (some
require `reasoning_content`, some reject it). The OpenAI-compatible adapter keeps
reasoning it received in the record and does not send it; reasoning from another
family is dropped with `ReasoningDropped`, as PRV-13 requires. The Anthropic
adapter replays its own thinking blocks, signed or redacted, and nothing else.

**Unparsable arguments stay with the call.** `ToolUseBlock.malformed` holds the
raw text when the arguments are not a JSON object even after repair. The pipeline
turns it into a validation error for the model (TOOL-2), and the adapter sends
the raw text back unchanged, so the model sees what it wrote.

**Text-call repair reads the whole reply by default.** A reply is taken as a tool
call only when all of it is one JSON object naming a known tool, fenced or not. A
model explaining some JSON is never taken to be calling a tool. Looking inside
prose happens only for servers configured with `native_tools = false`, where text
is the only way to call a tool.

**Retries stop at the first byte.** 408, 409, 429, 5xx and 529 are retried with
full-jitter exponential backoff, up to four attempts; `Retry-After` wins when it is
at most 60 s, and beyond that the error is reported, not waited out. Once a body
starts streaming nothing is retried, because its deltas have already reached the
user. A mid-stream error event is a `ProviderError`.

**Cost is exact, reported, free or unknown.** `usage.input_tokens` counts every
input token, cached ones included. Adapters price with a small shipped table dated
`pricing.CHECKED`, overridden by `[pricing."provider/model"]`; OpenRouter's own
reported cost wins where it is given; Ollama is free (`cost_source = "free"`).
Anything else is `None`, carried through `RequestFinished` and `TurnFinished` as
"unknown". A missing price is never counted as zero (BUD-5).

**Token counts are approximate, corrected by what the provider reports (OQ-3).**
There are no per-provider tokenisers. An adapter counts characters over four and
scales the count by the ratio between the provider's last reported input tokens
and its own estimate for the same request. The ratio also absorbs the tool
schemas sent with each request. Exact wherever usage comes back, close enough
before, and nothing to download.

**Cassettes are synthetic until recorded.** No keys were available when M2 was
built, so every cassette entry was written from the providers' documented wire
formats (`tests/support/wire.py`) and says `"source": "synthetic"`.
`just record-cassettes --only NAME` replaces an entry with a live exchange marked
`recorded <date>`. Error scenarios (401, 429, cancellation) and the fenced
tool-call case stay synthetic, since nobody triggers those on purpose. A test
fails the build if any cassette holds something shaped like a key.

**The fake provider is not in the contract suite.** The suite tests wire
translation, and the fake has no wire. Its behaviour is covered by the loop tests
that rely on it. `compat`, the user-defined provider, runs against a real HTTP
server on loopback. The socket guard lets through only that server's exact
address, so a stray request to a local Ollama on its default port still fails.

**Azure uses the deployment path.** URL `…/openai/deployments/{model}/chat/completions?api-version=…`,
key in an `api-key` header, `api_version` defaulting to `2024-10-21` and
overridable. The endpoint comes from `base_url` or `AZURE_OPENAI_ENDPOINT`, never a
default (PRV-15).

**Anthropic marks two cache breakpoints.** One on the system prompt, which caches
the tool schemas before it, and one on the last message, so each request in a turn
reads the previous request's prefix from the cache (PRV-8). Extended thinking is
requested only when `[providers.anthropic] thinking_budget` is set, and never
with `reasoning=False`.

## Consequences

- One `ProviderSection` dataclass is both the schema of `[providers.NAME]` and
  the set of quirk overrides, so a new quirk is one field in two places, and a
  test keeps the two in step.
- The contract suite's synthetic cassettes encode our beliefs about each API.
  Until they are recorded they catch regressions in our code, not mistakes in
  those beliefs. The scheduled live smoke run (TESTING.md layer 5) is what checks
  the beliefs.
- A server that silently ignores tools, rather than refusing them, looks like a
  model that never calls any. Neither edgar nor a probe request can tell those
  apart.

## Rejected alternatives

**A probe request per model.** It costs a request, and money, on every new model,
and reaches a host before the user's first prompt. The refusal carries the same
information for free.

**Per-provider tokenisers.** Exact counts before the first response, for a
download per provider and a dependency the budget does not have (NFR-5). Counts
only need to be exact at the compaction threshold, and by then usage has come
back.

**Replaying `reasoning_content` to servers that accept it.** It is right for some
servers and a 400 for others. What would change the answer: one field every
major compatible server agrees on.
