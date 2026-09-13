# ADR-0002 — Two adapters for five providers

**Status:** Accepted · 2026-09-02

## Context

edgar must talk to OpenAI, Azure OpenAI, OpenRouter, Ollama and Anthropic.
Understanding how providers genuinely differ, in tool-call shapes, streaming
formats, reasoning blocks, system prompt placement and caching, is one of the most
valuable things this project can teach. It is also the layer that breaks most often.

## Options

**A. One adapter per provider.** Five modules, maximum explicitness, maximum
learning. Five maintenance surfaces and substantial duplication, since four of the
five speak dialects of the same protocol.

**B. Wrap a library** such as LiteLLM. Working code on day one, 100+ providers,
free retries and cost tables. Costs a heavy dependency against the startup budget,
hides the exact mechanism the project exists to expose, and puts someone else's
normalisation layer between you and a malformed tool call at debug time.

**C. Hybrid.** One adapter for the OpenAI-compatible family, driven by a quirks
table, plus a dedicated Anthropic adapter.

## Decision

Option C. Two adapters, five providers.

`openai_compat.py` serves OpenAI, Azure, OpenRouter and Ollama. Their differences
are expressed as **data in a quirks table**, not as control flow: base URL, auth
style, whether the model name is a deployment name, whether tools are supported at
all, whether usage arrives in the final chunk, where cost comes from.

`anthropic.py` is separate because the Messages API differs structurally, not
cosmetically: content blocks rather than a string, `tool_use` and `tool_result` as
first-class blocks, system prompt as a top-level parameter, `cache_control`
markers, and thinking blocks with signatures that must be replayed intact.

A library remains available as an optional extra for exotic providers, behind the
same `Provider` protocol, but is not a core dependency.

## Consequences

- Adding a provider means one module plus one registry entry [PRV-11], or often
  just a new quirks entry
- The quirks table is **load-bearing, not cosmetic**. "OpenAI-compatible" is a
  spectrum, not a standard: Ollama's tool support varies per loaded model,
  OpenRouter passes through provider-specific behaviours, Azure needs deployment
  names and API versions
- Ollama's `supports_tools: "per-model"` is probed once and cached rather than
  assumed, because assuming is how you get a silent failure
- The provider **contract suite** (ADR-0009) becomes essential: one set of tests
  every adapter passes identically is what prevents "works on OpenAI, breaks on
  Ollama"
- Capabilities are declared and degradation is explicit [PRV-10]. A model that
  cannot use tools produces a clear refusal, never a silently chat-only session

## Rejected alternatives

**Wrapping LiteLLM** was rejected on the teaching goal primarily and the startup
budget secondarily. If provider maintenance ever becomes a genuine burden on a
solo maintainer, revisiting this is legitimate, and the `Provider` protocol makes
a library-backed adapter a drop-in.

**Five separate adapters** were rejected as duplication that teaches the same
lesson four times.
