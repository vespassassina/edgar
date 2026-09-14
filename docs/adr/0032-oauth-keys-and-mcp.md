# ADR-0032 — OAuth for issuing keys and for MCP servers, never for subscriptions

**Status:** Accepted · 2026-09-13 · Moves MCP OAuth from v2 (ADR-0015) to v1; reaffirms the "not taken" on subscriptions in DECISIONS.md · Amended by ADR-0043 (GitHub Copilot, the one documented exception)

## Context

The maintainer had no API credit and asked whether edgar could use a Claude
subscription instead. It cannot: Anthropic's terms keep subscription sign-in for
Anthropic's own products, and it has cut off third-party harnesses that used it
(research/hn-2026-09.md, "Subscriptions no longer usable in third-party
harnesses"). DECISIONS.md already lists subscriptions as not taken.

That still leaves two uses of OAuth that the spec either lacks or schedules late:

- Some providers **issue an API key through an OAuth flow**. OpenRouter does
  this with PKCE: the user approves in the browser, and edgar receives a key the
  user controls and can revoke. This is a better experience than copying a key,
  and the terms allow it.
- **Remote MCP servers** authenticate with OAuth 2.1 under the MCP authorization
  spec. TOOL-7 put that in v2, which leaves remote servers with static headers
  for a whole tier.

## Options

**A. Keys and MCP, no subscriptions.** `edgar login` for providers that hand out
keys through OAuth, and MCP OAuth moved to v1 alongside MCP. Subscriptions stay
out. It is within every vendor's terms, and one mechanism serves both uses.

**B. A plus subscriptions where a vendor's terms allow it.** More users could run
without buying API credit. But it has to be checked vendor by vendor and re-checked
when terms change, and edgar ends up depending on consumer plans that can be
withdrawn overnight: the lock-in the field review warns about.

**C. Plan only.** Write the design and decide later. Cheap, but it leaves the
remote-MCP gap open with no date.

## Decision

**A.** Chosen by the maintainer on 2026-09-13.

- **`edgar login PROVIDER` and `edgar logout PROVIDER`** [PRV-18], Core (M6).
  OAuth 2.0 authorization code with PKCE and a loopback redirect on `127.0.0.1`
  (RFC 8252), or device code where the provider offers only that. Before opening
  the browser, edgar prints the exact host it will contact; login is an explicit
  user action to a named host, so PRV-15 holds.
- **Which providers.** Only those that issue an API key through OAuth, listed in
  `quirks.py` as data (`oauth = {...}`). OpenRouter is the first; each one is
  checked against the provider's current documentation when it is added.
- **Where the credential lives.** In the OS keyring, through the optional
  `keyring` extra [CFG-6]; never in a config file, never in the transcript,
  events or logs. Without the extra, `edgar login` prints the key once with the
  `export` line to use, and stores nothing. A stored key is read exactly like one
  from `api_key_env`, so the adapters do not change.
- **MCP OAuth** [TOOL-7], v1 (M8), with MCP: OAuth 2.1 with PKCE, discovery
  through protected-resource metadata, tokens in the keyring, refreshed in the
  transport. Project MCP servers still need `edgar trust` (PERM-13).
- **Subscriptions: never.** No provider is signed in with a consumer plan. This
  is now a PRD non-goal as well as a DECISIONS.md entry.

## Consequences

- One new command pair, one table of OAuth endpoints as data, and the `keyring`
  extra earning its place in the dependency budget (NFR-5).
- **Load-bearing:** a login token is a secret like any key. The redaction that
  keeps `${env:…}` values out of the transcript (TOOL-6) must cover keyring
  values too, and a test must plant one and search every output for it.
- `edgar models list` shows "logged in" next to a provider whose key came from
  the keyring, so where a credential came from stays visible.
- Users without API credit are pointed to Ollama or a free hosted tier, not to a
  subscription. The README says so.
