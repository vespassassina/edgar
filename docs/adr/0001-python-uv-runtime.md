# ADR-0001 — Python 3.12 with uv-first distribution

**Status:** Accepted · 2026-09-02

## Context

edgar must run on Windows, macOS and Linux from one codebase, start fast enough to
be used in a pipe, and above all be readable by people learning how agent harnesses
work. Distribution has to be painless or nobody tries it.

## Options

**Python 3.12 + uv.** Largest pool of people who can read and contribute, richest
AI ecosystem, `uv tool install` and `uvx` give a real command on PATH with an
isolated environment on all three platforms. No true single binary.

**Go.** One static binary per OS, excellent CLI and concurrency story, fastest cold
start. Smaller overlap with the audience most interested in agent internals, and
more boilerplate per idea expressed, which works against the teaching goal.

**TypeScript.** `npx` distribution, good streaming ergonomics, huge contributor
pool. Node runtime dependency, and async complexity that tends to obscure control
flow in exactly the code a reader most needs to follow.

**Rust.** Fastest and safest, single binary. Steepest curve, and the borrow
checker's demands would dominate the codebase's shape over clarity.

## Decision

Python 3.12+, distributed uv-first.

- **Primary:** `uv tool install edgar-cli` and `uvx edgar-cli`
- **Secondary:** PyApp-built binaries attached to GitHub Releases per platform
- **Tertiary:** Docker image
- **Noted:** `pipx` works and is documented, not promoted

PyInstaller and Nuitka are rejected for v1. PyInstaller onefile self-extracts to
temp on every launch, adding hundreds of milliseconds to exactly the piped
invocations we care about, and it triggers Windows Defender false positives that an
unsigned OSS project cannot fix. Nuitka is technically better but adds real build
complexity for a benefit uv already delivers.

## Consequences

**Accepted cost:** "one install command" instead of "one file". For a
developer-audience CLI in 2026 this is a small gap, and uv closes most of it.

**Load-bearing consequence:** the real risk is not packaging, it is **startup
latency**. CPython starts in roughly 30 ms; imports decide the rest. Eagerly
importing provider SDKs, pydantic and rich puts first output past 400 ms. So:

- Provider modules are imported lazily behind a registry (ADR-0002)
- `rich` and `prompt_toolkit` are never imported on the `-p --json` path
- NFR-1 sets a 150 ms budget, enforced by a CI test using `-X importtime`
  from milestone 1, before there is anything to regress

That constraint is a design benefit, not just a check: it forces the provider and
CLI layers to stay thin.

## Rejected alternatives and their triggers

Go remains the correct choice if a genuinely self-contained single binary ever
becomes a hard requirement rather than a preference. It is not close. This ADR
should be revisited if users report distribution as a real blocker, or if NFR-1
proves unachievable without contorting the code.
