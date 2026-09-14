# ADR-0043 — GitHub Copilot as a provider, signed in with edgar's own OAuth app

**Status:** Accepted, shipping gated on GitHub's terms · 2026-09-14 · Amends ADR-0032 (the one exception to "subscriptions: never") and PRD §5.2; adds PRV-19

## Context

The maintainer asked for a GitHub Copilot provider: a Copilot subscription gives
access to many models, and signing in should be OAuth.

ADR-0032 says edgar never signs in with a subscription. The reason was
Anthropic's terms, which keep subscription sign-in for Anthropic's own products,
and the cut-offs of harnesses that used one anyway. GitHub's position differs,
as checked on 2026-09-14:

- GitHub supports Copilot Pro, Pro+, Business and Enterprise subscriptions in
  OpenCode, a third-party terminal agent, through a named partnership and a
  device login ([changelog, 2026-01-16](https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/)).
- The Copilot SDK (GA, MIT) lets any third-party app use a user's Copilot
  subscription with the app's own OAuth app or GitHub App token
  ([GitHub OAuth setup](https://docs.github.com/en/copilot/how-tos/copilot-sdk/setup/github-oauth)).
- GitHub has **not** documented that any app may call the Copilot model
  endpoint directly. OpenCode is the only third-party client named. Tools that
  reuse another product's OAuth client id are unofficial.

So a subscription is sanctioned in principle, but the exact route edgar would
take is documented only for one partner.

## Options

**A. Call Copilot's endpoint directly, signed in with edgar's own OAuth app.**
The flow:
1. `edgar login github-copilot` runs GitHub's device flow with an OAuth app
   registered under edgar's name.
2. The token goes to the keyring.
3. The provider is a row in `quirks.py` on the OpenAI-compatible adapter.

It fits the one loop (ADR-0006) and ADR-0020's rule that differences are data.
It costs about 80 lines of code. Its risk is that the direct route is not in
GitHub's documentation for anyone but OpenCode.

**B. The Copilot SDK, as a separate plugin package.** The SDK is fully official.
But it drives the Copilot CLI's own agent runtime, so a second loop would call
edgar's tools, outside edgar's permissions, verify gate and events. That breaks
ADR-0006.

**C. Plan only, and decide at M8.** It leaves the request open.

## Decision

**A**, chosen by the maintainer on 2026-09-14, with a gate before shipping.

- **Sign-in** [PRV-19]. `edgar login github-copilot` uses GitHub's OAuth device
  flow, which suits a terminal and needs no loopback port.
  - The client id is edgar's own registered OAuth app, never a client id
    borrowed from another product. It sits in the quirks row, since a public
    client id is not a secret.
  - edgar prints the host (`github.com`) and the one-time code before polling.
  - The token goes to the OS keyring (CFG-6) and is redacted like any key
    (ADR-0032's load-bearing test covers it). `edgar logout github-copilot`
    removes it.
  - This shares ADR-0032's login code, so it lands in M8 with `edgar login`.
- **Requests.** A `github-copilot` row in `quirks.py` holds the base URL, the
  headers Copilot requires, and the token source. Model strings are
  `github-copilot/<model>`, for example `github-copilot/claude-sonnet-5`.
  - Business and Enterprise plans use their own base URL, chosen by a
    `[providers.github-copilot]` override, not by a branch in code.
  - Models that Copilot serves only on the Responses API are marked in the row
    and refused with a clear message until the adapter speaks that API.
- **Models.** `edgar models` lists what the subscription offers, from Copilot's
  model list, on request only (as for other providers, CLI-23). Nothing is
  fetched at startup.
- **Cost.** Copilot bills in premium requests, not dollars, so each request's
  dollar cost is "unknown" (PRV-6).
  - Under a cost cap, the existing rule applies: a model of unknown price stops
    at once. `[pricing."github-copilot/…"]` can set a price.
  - `/cost` also counts requests per model. Showing Copilot's premium-request
    multipliers is an open detail for M8.
- **The gate.** Before this ships, the maintainer:
  1. registers the OAuth app on their GitHub account;
  2. checks GitHub's current terms, or asks GitHub, that a registered app may
     call the Copilot endpoint directly.

  If the answer is no, this ADR is superseded by option B or dropped. The code
  and docs stay unreleased until then.
- **Every other subscription is still never.** ADR-0032's rule stands for every
  vendor without a documented allowance. Each exception gets its own ADR, citing
  the vendor's own documentation.

## Consequences

- PRD §5.2's non-goal now reads "except where the vendor documents that third
  parties may use it (GitHub Copilot, ADR-0043)". The README's "API keys, not a
  vendor's subscription" line changes when this ships, not before.
- **Load-bearing:** the client id is edgar's own. Borrowing another product's
  id impersonates it, and the whole case for this ADR rests on edgar being
  honestly identified.
- The provider depends on terms that GitHub can change. If GitHub withdraws
  access, the provider is removed in the next release, and users keep every
  other provider unchanged. This is the lock-in ADR-0032 warned about,
  accepted knowingly and kept to one row of data.
- About 80 lines of code against v1's budget, most of it the device flow, which
  `edgar login` can reuse for any provider that offers one.

## Rejected alternatives

**B** would be the answer if the SDK let an app run one model turn with its own
tools, without Copilot's agent loop. Revisit if GitHub adds that, or if the gate
above comes back "SDK only".

**Reusing an existing client id** (as some unofficial tools do) was not
considered: it misidentifies edgar to GitHub and is the likeliest way to get
users' accounts flagged.
