# ADR-0048 — Signing in as built

**Status:** Accepted · 2026-09-14 · Completes M8; implements ADR-0032 and
PRV-18, refines ADR-0047

## Context

The second half of M8 is the sign-in that ADR-0032 specified: OAuth 2.1 with
PKCE for remote MCP servers, tokens in the OS keyring, and `edgar login
PROVIDER` / `edgar logout` for a provider that hands out an API key the same way
(OpenRouter first) [PRV-18, CFG-6]. It cost 317 lines of code in a new `auth/`
package; `src/` is at 6,809 of v1's 8,000.

Three things made the decisions: a terminal program has no redirect URI of its
own, edgar has no client id registered with anyone, and a sign-in is the one
moment where a harness that promises no hidden hosts is about to open a browser.

## Options and decisions

**1. Where the redirect goes.** The alternatives are a device-code flow (the
user types a code on another device), a hosted callback on a domain edgar owns,
and a loopback listener. **Decided: loopback on 127.0.0.1, on a port the OS
picks** (RFC 8252 §7.3, `oauth.listen()`). A hosted callback would mean edgar
runs a server that sees authorization codes, which contradicts the promise that
nothing goes anywhere the user did not configure; device code needs the
authorization server to support it and most MCP servers do not. Port 0 means
nothing is reserved, two sign-ins can overlap, and no firewall rule is needed.

**2. When the port is opened.** The obvious shape is "build the URL, then
listen". **Decided: listen first, then build the URL.** Dynamic client
registration must declare the exact redirect URI, and the port is only known
after the socket is open. `oauth.grant()` (listen and visit in one call) stayed
for the provider flow, which registers nothing.

**3. Who edgar is to a server.** edgar ships no client id and no client secret,
and never will: a public program cannot keep one. **Decided: RFC 7591 dynamic
client registration, `token_endpoint_auth_method: "none"`, PKCE as the only
proof.** The client id a server issues is kept next to the token, so a second
sign-in reuses it. A server that registers no clients fails with a message
saying to ask its operator for a client id and put it in `headers` instead;
edgar does not invent one.

**4. What a turn may do.** A remote MCP server whose token is missing or expired
could, in principle, open a browser mid-turn. **Decided: never.** The call fails
like any tool failure, with `edgar mcp login NAME` in the message; a human runs
that command. A turn that opens a browser is a turn doing something the user did
not ask for, and in `-p` or a subagent there is nobody to approve it. This is why
`auth/` is reached from the transport only to *read* a token, never to get one.

**5. Which token, for which server.** **Decided: RFC 8707 `resource` on both the
authorization request and the exchange**, so the token a server issues is for
that MCP server and not a bearer token for everything behind that authorization
server. Discovery follows the chain the specification defines: RFC 9728
protected-resource metadata on the MCP URL, then RFC 8414 (or OpenID) metadata on
the authorization server it names.

**6. Where a secret lives.** **Decided: the OS keyring, through the optional
`keyring` extra, and nowhere else** [CFG-6]. There is no token file, because a
file is what leaks. With no keyring installed, `edgar login` prints the key once
and says it kept nothing, rather than writing it somewhere the user did not
expect. Every token is registered with `scrub()` the moment it is written *or*
read back, so a token planted in the keyring by anything else is still redacted
from transcripts, events and logs [TOOL-6]. Accounts share one namespace,
`provider:NAME` and `mcp:URL`, so `edgar logout` and `edgar mcp logout` see the
same store.

**7. A provider's own key exchange.** OpenRouter's is not OAuth: a `callback_url`
parameter instead of `redirect_uri`, JSON instead of form encoding, a `key` in the
answer instead of `access_token`. **Decided: a row in `quirks.py`**, like every
other provider difference (ADR-0002) — an `OAuth` dataclass naming the two URLs,
the callback parameter, the encoding and the field to read. A second provider is a
row, not a branch. `connect()` looks in the keyring after the environment, so a
key from `edgar login` needs no `OPENROUTER_API_KEY`, and the error when both are
missing names the command to run.

## Consequences

- `edgar login PROVIDER`, `edgar logout PROVIDER`, `edgar mcp login NAME` and
  `edgar mcp logout NAME` exist; `edgar models list` says which providers are
  signed in.
- `keyring` is an optional extra, absent from the startup import ban's reach
  because nothing on the fast path imports it (NFR-1).
- GitHub Copilot [PRV-19, ADR-0043] remains gated on GitHub's terms and is not
  built.
- Tests cover the whole flow with no browser and no network: a keyring that is a
  dictionary, a loopback client that plays the browser, and every HTTP exchange
  supplied by the test (`tests/integration/test_login.py`).
