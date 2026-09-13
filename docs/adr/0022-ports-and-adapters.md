# ADR-0022 — One core, ports for everything outside it, one distribution

**Status:** Accepted · 2026-09-13 · Amends ADR-0018 (Python plugin surfaces)

## Context

The question: should the model and provider adapters be split from the harness,
and the same for tools, skills and everything outside the core, so that each has an
interface with several possible implementations?

Two things are easy to conflate here. **Separating interfaces** (a core that
depends only on protocols, with implementations behind them) and **separating
distributions** (one package or repository per adapter, as LangChain and similar
projects did). The first is about design; the second is about packaging, release
and trust.

Constraints that bear on it:

- The goal is lightweight, extensible, open and easy to use
- Startup must not pay for adapters that are not used (ADR-0012)
- The provider-abstraction library LiteLLM had releases compromised on PyPI in
  March 2026 through its CI pipeline (docs/research/hn-2026-09.md). Every package
  is a publishing credential and a pipeline that can be attacked
- The project is maintained by one person and must be readable in an afternoon

## Options

**A. Status quo.** Protocols exist for providers and tools; the rest is concrete.

**B. Split distributions.** `edgar-core`, `edgar-openai`, `edgar-anthropic`,
`edgar-mcp`, `edgar-tools-fs`, and so on. Maximum modularity. Costs a version
matrix (which core works with which adapter), more publishing credentials and CI
pipelines to secure, a longer install story, and a reader who has to jump between
repositories to follow one request.

**C. Ports and adapters inside one distribution.** A small core that imports no
adapter; named ports with protocols; built-in adapters in the same package, loaded
lazily; third-party adapters through entry points. The layering is enforced by a
test, so a later split is mechanical if it is ever needed.

## Decision

Option C.

**The core** is `core/`, `context/`, `permissions/` and `tools/execute.py`: the
loop, the message vocabulary, events, the verify gate, compaction and `decide()`.
It imports no adapter module. Adapters import core types and nothing from each
other. A CI test enforces both rules, alongside the tier-isolation test (NFR-12).

**The ports:**

| Port | Protocol | Built-in adapters | Third-party adapters | Tier |
|---|---|---|---|---|
| **Provider** | `providers/base.Provider` | `openai_compat`, `anthropic`, `fake` | config block (PRV-12); entry point `edgar.providers` | Core; plugins v1 |
| **Tool source** | `tools/base.Tool` | built-in, command, HTTP, MCP | TOML files; MCP servers in any language | Core; MCP v1 |
| **Skill source** | files | `SKILL.md` folders, extensions | files | Core |
| **Sandbox** | `sandbox/base.Sandbox` | `none`, `bwrap` (Linux), `seatbelt` (macOS), `container` (Docker or Podman, any OS) | entry point `edgar.sandboxes` | v1 |
| **Retriever** | `memory/retriever.Retriever` | `fts5` | entry point `edgar.retrievers` | port v1; plugins v2 |
| **Output** | event-bus subscriber | renderer, status line, `--json`, `--events` | `edgar.run()` subscribers | Core |

**Not ports, on purpose:**

- **Session storage.** JSONL plus SQLite is the interface, not an implementation
  detail: `tail -f`, `jq`, session search and other tools reading the files depend
  on it. A pluggable store would make the format unknowable
- **Tools in Python.** MCP already covers code-bearing tools in any language
  (ADR-0018)
- **The permission engine.** Pluggable security is no security. Hooks can veto;
  nothing can replace `decide()`

**One distribution.** `edgar-cli` ships the core and every built-in adapter.
Optional extras cover optional dependencies (`keyring`). Entry points are read only
when a name misses the built-in and configured tables, so installed plugins cost
nothing on the common path.

**The Sandbox port** answers the isolation finding. `shell.sandbox` selects a
backend for `shell`, command tools and the verify command:

```python
class Sandbox(Protocol):
    name: str
    def available(self) -> bool: ...                          # detect at startup, cheaply
    async def run(self, argv: list[str], *, cwd: Path, env: dict[str, str],
                  writable: list[Path], network: bool, timeout_s: float) -> ProcessResult: ...
```

The default stays `none` with a `doctor` recommendation, because a sandbox that
fails to start on half the machines is worse than an honest default. `writable`
is the project directory plus the session's blob directory; `network` follows the
permission decision. Backend tests run where the backend exists; core tests use a
fake sandbox and run everywhere, so NFR-6 holds for the core.

## Consequences

- **Anyone can add an implementation without a fork:** a provider as a config block
  or a package, a sandbox or a retriever as a package, a tool as a file or an MCP
  server
- **One thing to install, one thing to trust.** Five required dependencies, one
  publishing pipeline to harden
- **The reader follows one request through one repository**
- **Load-bearing:** the core never imports an adapter. If `core/loop.py` starts
  importing `openai_compat` "just for a type", the ports become decoration. The
  import test holds the line
- **ADR-0018 is amended:** Python plugin surfaces are providers, sandboxes and
  retrievers. Tools stay files and MCP

## Rejected alternatives

**B (split distributions)** is rejected for now on supply-chain surface, install
friction and readability. **What would change the answer:** a third party that
wants to embed only the loop without the CLI (then publish `edgar-core` from the
same repository), or a provider adapter that needs a release cadence independent of
the core because the provider's API keeps drifting. Because the layering is already
enforced, either split is a packaging change, not a refactor.

**Pluggable session storage** is rejected: the file format is part of what makes
edgar open.

**Pluggable permission engines** are rejected: the security boundary must be the
same code for everyone who reads the docs.
