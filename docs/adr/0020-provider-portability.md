# ADR-0020 — Any OpenAI-compatible endpoint, reasoning blocks tagged by origin

**Status:** Accepted · 2026-09-13 · Amends ADR-0002 and ADR-0013

## Context

Three provider questions were left open by v0.2.

**Openness.** Five named providers is a good tested set, but many people run models
behind other OpenAI-compatible servers: LM Studio, vLLM, llama.cpp, hosted
inference services. Each would need a code change to reach.

**Switching models mid-session.** ADR-0013 allows fallback and escalation, and its
example escalation chain moves from an OpenAI model to an Anthropic one. Reasoning
does not travel between them. Anthropic thinking blocks carry signatures only
Anthropic can verify, OpenAI's reasoning state is its own, and some providers
reject a tool-use turn that lacks their own reasoning block when reasoning is
enabled. "Capabilities at least equal" (ROUTE-7) does not cover this.

**Which OpenAI API.** The shared adapter speaks Chat Completions, because that is
what every OpenAI-compatible server implements. OpenAI's own reasoning models are
better served by its Responses API, which can carry reasoning across the tool calls
of a turn. Over Chat Completions they re-reason at each step, which costs tokens
and latency. That trade was implicit.

## Options

**A. Status quo.** Five providers, cross-family switching undefined, Chat
Completions implicitly.

**B. Data-defined providers, origin-tagged reasoning, an explicit API choice.**

**C. Normalise reasoning into plain text** so it can be replayed anywhere. Loses
signatures, which Anthropic requires intact, and puts one model's private reasoning
in front of another.

## Decision

Option B.

**User-defined providers are config, not code** [PRV-12]:

```toml
[providers.lmstudio]
kind = "openai-compatible"
base_url = "http://localhost:1234/v1"
api_key_env = "LMSTUDIO_API_KEY"      # optional
supports_tools = "per-model"          # any quirk may be set; defaults are conservative
```

`lmstudio/qwen3-coder` then resolves through `openai_compat.py` with those quirks.
The five named providers stay first-class, with cassettes and the live smoke job.
User-defined ones are capability-probed on first use and documented as best effort.
Anything needing code becomes a provider plugin (ADR-0018).

**Reasoning is tagged by origin** [PRV-13]. `ThinkingBlock` gains
`origin: str`, the adapter family and model that produced it. When serialising a
request, an adapter includes only thinking blocks whose origin matches its own
family and drops the rest, emitting one `ReasoningDropped` event per switch.

**Switching family mid-turn disables reasoning until the next user turn.** When
fallback or escalation moves to a different adapter family while a turn is in
progress, the new model runs with reasoning off for the rest of that turn, so no
provider sees a tool-use turn missing its own reasoning block. Both `ModelFellBack`
and `ModelEscalated` say so in the status line. Switches within one family keep
reasoning.

**Chat Completions for the whole OpenAI-compatible family, in Core.** It is the one
protocol every compatible server speaks, which is what makes the openness above
possible. The known cost for OpenAI's reasoning models is recorded here. A
Responses API adapter (`openai_responses.py`) is a sanctioned optional third
adapter, selected by the quirk `api = "responses"`. It is added when an eval shows
the gap matters on tool-heavy tasks, and in v2 at the latest (OQ-8).

## Consequences

- **Adding a provider can be zero code**: one TOML block for any compatible server,
  one module plus one registry entry for anything else [PRV-11]
- **Fallback and escalation are safe across families** at the cost of reasoning for
  the rest of one turn, and that cost is visible
- **The contract suite grows** two tests: foreign reasoning is dropped on
  serialisation, and a mid-turn family switch produces a request the target
  accepts
- **"Two adapters" becomes "two adapters, one optional third".** The teaching point
  survives: differences are data where they can be, code where the protocol truly
  differs
- **Load-bearing:** thinking blocks are never rewritten, merged or re-signed. They
  are kept intact for their own family or dropped

## Rejected alternatives

**A** is rejected because an undefined cross-family switch is a 400 waiting for the
first escalation in production.

**C (reasoning as plain text)** is rejected: it breaks Anthropic's signature check
and leaks one model's reasoning into another's prompt.

**Making Responses the default for OpenAI now** is rejected for Core. It adds an
adapter before the eval set exists to show it is needed. Revisit when the eval set
(TESTING layer 6) has tool-heavy tasks to measure it on.
