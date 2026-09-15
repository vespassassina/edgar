# ADR-0049 — A link-local hard layer for network tools

**Status:** Accepted · 2026-09-14 · Adds PERM-16

## Context

A pre-launch review of the repository, done the way a Hacker News reader would
read it, found a real gap: `fetch` and any HTTP tool have no guard against the
cloud instance-metadata endpoint. In `auto` mode, before the session is tainted,
`decide()`'s `_mode()` falls through to a plain `Allow()` for `kind == "network"`.
A model steered by injected content, or simply asked to "check what's on this
machine", can `fetch("http://169.254.169.254/latest/meta-data/iam/security-credentials/…")`
and read the cloud credentials of whatever VM or container edgar runs in. Every
major cloud (AWS, GCP, Azure, DigitalOcean, Oracle Cloud) serves this at the same
address, which is what makes it worth a dedicated rule rather than "add it to
`shell_deny` and move on": there is one address that matters, and it is a literal
IP, not a pattern to guess.

The obvious first instinct — deny anything that resolves to a private or loopback
address — collides with how the offline suite fakes "the internet": FixtureServer
(`tests/support/fixture_server.py`) binds a real `ThreadingHTTPServer` to
`127.0.0.1` and tests point `fetch` at it to exercise taint, permission prompts and
untrusted content honestly, without a mock at the `httpx` layer. A guard that
blocks all loopback addresses would make every one of those tests fail, or force
a test-only bypass into production code, which `tests/support/netguard.py`
explicitly says is not how this project draws that line ("Production code has no
test switch; the guard lives entirely here").

## Options

**A. Block loopback and link-local together**, matching the review's first-pass
wording ("169.254.169.254, localhost"). Closes the most obvious reading of the
threat but breaks the FixtureServer pattern used across `test_safety.py`,
`test_login.py` and `test_mcp.py`, and a real user pointing `fetch` at a local dev
server (`http://localhost:3000/api`) is common enough that blocking it outright
would be a worse false positive than the risk it prevents.

**B. Block link-local only** (169.254.0.0/16, fe80::/10). This is exactly the
range the metadata convention lives in and nothing else does; no legitimate
`fetch` target should ever be a link-local literal. Loopback stays untouched, so
FixtureServer and a locally running dev server both keep working.

**C. Resolve the hostname and check the resulting address**, closing the "a
hostname that resolves there" gap Option B leaves open (DNS rebinding, or a
domain someone points at 169.254.169.254 on purpose). Needs a DNS lookup inside a
pure function, or threading the result in from an async caller; either way it is
real complexity for a threat `auto` mode's taint tightening and the documented
container recommendation already partly cover, and it still would not stop the
`shell` tool from doing the same `curl`.

## Decision

Option B. `permissions/matcher.py` gains `link_local(url) -> bool`: it reads only
the URL's literal host with `urlsplit`, and returns `ipaddress.ip_address(host)
.is_link_local` when that parses, `False` otherwise (including for every
hostname, `localhost` included — no DNS lookup happens). `permissions/policy.py`
checks it in the hard layer, beside the catastrophic-command check and before the
`yolo` early return, so a link-local `fetch` (or a custom HTTP tool, since both
share `category == "network"`) is denied in every mode, `yolo` included [PERM-16].

## Consequences

- Closes the single highest-value SSRF target — cloud credential theft through
  the metadata endpoint — for both modes where it mattered most (`auto` before
  taint, and `yolo`, which nothing else in the hard layer skips for network calls)
- **What remains**, stated plainly: a hostname that merely resolves to a
  link-local address still gets through (`test_a_hostname_that_merely_resolves_there_is_not_caught`
  documents this); the `shell` tool can run `curl` against the same address and
  nothing here stops it (PERM-14's "speed bump, not a boundary" already says so);
  private ranges (10.0.0.0/8, 192.168.0.0/16) and loopback are untouched on
  purpose, so a `fetch` at an internal service on those ranges is still a plain
  mode decision, not a hard denial. The real boundary for untrusted work is still
  the documented container recipe (ADR-0021's rejected alternative B), not this
  check
- No test doubles change: FixtureServer keeps binding to loopback, and no
  test-only bypass was added anywhere in `src/`
- Costs about a dozen lines of code in `matcher.py` and two in `policy.py`

## Rejected alternatives

**A (loopback and link-local together)** is rejected because it would make
"point edgar at a local dev server" and the project's own way of testing
untrusted content both fail, for a security property that live DNS resolution
would not actually reach anyway (see C).

**C (resolve and check)** is rejected for Core and v1: it needs I/O inside what
is otherwise a pure decision function, or an async plumbing change to
`permissions/guard.py`, for a threat that DNS rebinding research generally
addresses at the network layer (pinning the resolved address for the actual
connection), not the URL-string layer edgar's permission engine works at.
Revisit if a sandboxed network policy (PERM-15, `shell.sandbox`) grows a way to
enforce this at the socket instead.
