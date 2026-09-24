# Architecture Decision Records

Numbered, immutable once accepted. Superseding an ADR means writing a new one that
references it, not editing the old one. The Status column below records which
later ADRs amend an earlier one; read them together.

Format: Context → Options → Decision → Consequences → Rejected alternatives.

[`../DECISIONS.md`](../DECISIONS.md) summarises the v0.3 revision (ADRs 0015–0021)
and the v0.4 field review (ADRs 0022–0025) in one page, including the smaller fixes
that did not need an ADR.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-python-uv-runtime.md) | Python 3.12 with uv-first distribution | Accepted |
| [0002](0002-provider-adapter-strategy.md) | Two adapters for five providers | Accepted · amended by 0020 |
| [0003](0003-mcp-in-v1.md) | MCP client in v1, no server mode | Accepted · amended by 0018 |
| [0004](0004-permission-model.md) | Four-mode policy engine, explicit mode when piped | Accepted · amended by 0021 |
| [0005](0005-tick-scheduling.md) | Tick model over daemon or emit-only | Accepted · v2 tier (0015); `schedule_self` storage per 0021 |
| [0006](0006-subagent-context.md) | Fresh context, parallel from v1 | Accepted |
| [0007](0007-memory-architecture.md) | Four surfaces, SQLite store with markdown interface | Accepted · amended by 0017, reaffirmed by 0024 |
| [0008](0008-controller-guardrails.md) | Deterministic triggers, typed proposals, tighten-only | Accepted · amended by 0017 (`learn` removed) |
| [0009](0009-testing-strategy.md) | Offline-first with contract suite and scheduled live smoke | Accepted |
| [0010](0010-session-storage.md) | JSONL transcripts with SQLite indices | Accepted · compaction records per 0016 |
| [0011](0011-events-not-callbacks.md) | Event bus for all output | Accepted |
| [0012](0012-startup-budget.md) | 150 ms startup as an enforced constraint | Accepted · import list per 0019 |
| [0013](0013-model-routing.md) | Routing, escalation and fallback are three mechanisms | Accepted · amended by 0020 |
| [0014](0014-verification-and-skill-synthesis.md) | Verify before done, synthesise skills only from verified work | Accepted · amended by 0017 |
| [0015](0015-release-tiers.md) | Ship in three tiers: Core, v1, v2 | Accepted |
| [0016](0016-context-pipeline.md) | Context is compressed in stages, cheapest first, on whole units | Accepted |
| [0017](0017-learning-boundary.md) | Only human-typed text and harness-computed errors create active facts | Accepted |
| [0018](0018-extension-model.md) | Tools, skills and extensions: one vocabulary, files first, Python last | Accepted · plugin surfaces amended by 0022 |
| [0019](0019-dependency-budget.md) | Five required dependencies | Accepted |
| [0020](0020-provider-portability.md) | Any OpenAI-compatible endpoint, reasoning tagged by origin | Accepted |
| [0021](0021-humans-widen-machines-tighten.md) | Humans widen, machines tighten: taint, control files, project trust | Accepted |
| [0022](0022-ports-and-adapters.md) | One core, ports for everything outside it, one distribution | Accepted |
| [0023](0023-no-hidden-behaviour.md) | No hidden behaviour: no implicit hosts, the prompt is a file, the prefix is stable | Accepted |
| [0024](0024-lexical-memory.md) | Memory stays lexical; a retriever port for embeddings or graphs | Accepted |
| [0025](0025-working-state.md) | Plans, todos and forks are session state, not prompts | Accepted |
| [0026](0026-licence-agpl.md) | License edgar under AGPL-3.0-or-later | Accepted |
| [0027](0027-distribution-name.md) | Distribute as `edgar-harness`; the command stays `edgar` | Accepted · amends the package name in 0001, 0019, 0022 |
| [0028](0028-input-during-a-turn.md) | Input during a turn: queue by default, steer on request, btw on the side | Accepted |
| [0029](0029-session-commands.md) | Session commands: append-only, rewind the conversation not the disk, no hidden titles | Accepted · `/resume` now pairs with `/pause` |
| [0030](0030-personality-file.md) | A personality file for tone and style, owned by the user | Accepted · complements 0023 |
| [0031](0031-provider-layer-as-built.md) | The provider layer as built: what the sketch left open | Accepted · refines 0002, 0009, 0020; resolves OQ-3 |
| [0032](0032-oauth-keys-and-mcp.md) | OAuth for issuing keys and for MCP servers, never for subscriptions | Accepted · MCP OAuth moves from v2 to v1 |
| [0033](0033-replan-after-m2.md) | The REPL before the safety milestone, and CLI and API tools with it | Accepted · order M4 before M3; custom tools and trust move to M3 |
| [0034](0034-model-picker.md) | A model picker that asks, lists on request, and never edits your config | Accepted |
| [0035](0035-repl-as-built.md) | The REPL as built: a prompt that never blocks, text a line at a time, no rich | Accepted · drops `rich` |
| [0036](0036-safety-layer-as-built.md) | The safety layer as built: one pure decision, a guard around it, and what moved | Accepted · `/browser` to M8 |
| [0037](0037-core-fits-in-5000.md) | Core stays under 5,000 lines: simplify first, then move four features to v1 | Accepted · plan and todo, save and load, login, daily cap to v1 |
| [0038](0038-context-and-sessions-as-built.md) | Context and sessions as built: records by position, S3 only past the window, three commands to v1 | Accepted · `/history`, `edgar cost`, `edgar context show` to v1 |
| [0039](0039-capability-broker.md) | A capability broker in v2: every tool call checked against a ticket bound to what the human typed, with a signed receipt | Accepted · new milestone M17 |
| [0040](0040-written-to-be-read.md) | Written to be read: pseudocode comments, shallow functions, every limit in lines of code, A Tour of the Harness | Accepted · the loop's limit is now lines of code |
| [0041](0041-skills-as-built.md) | Skills as built: the tool is the loader, a human's skill beats a learned one, a skill's `verify` moves to v1 | Accepted · amends PRD §5.1 |
| [0042](0042-skill-audit.md) | Audit a skill before it is copied in: deterministic checks decide, a model only advises | Accepted · adds SKL-18 (v1) |
| [0043](0043-github-copilot-provider.md) | GitHub Copilot as a provider, signed in with edgar's own OAuth app | Accepted, gated on GitHub's terms · amends ADR-0032, adds PRV-19 (v1) |
| [0044](0044-keyless-cloud-sign-in.md) | Sign in to Azure, Google Cloud and AWS through the cloud's own CLI | Accepted · adds PRV-20 (Core), amends CFG-6 |
| [0045](0045-memory-as-built.md) | Memory as built: one database, facts that never change, a gate at the end of the turn | Accepted · extends MEM-15 to facts |
| [0046](0046-forks-saves-and-the-daily-cap.md) | Forks, saved sessions and the daily cap as built: a fork is one line, a save travels redacted, the cap becomes the turn's | Accepted · completes M7 |
| [0047](0047-mcp-as-built.md) | MCP as built: `[mcp.NAME]` blocks, a config-hashed tool cache so no server starts at session start, deferred schemas listed in `tool_search`, results always untrusted | Accepted · first half of M8 |
| [0048](0048-signing-in-as-built.md) | Signing in as built: PKCE on a loopback port opened before registration, dynamic client registration, tokens in the OS keyring, and a turn that never opens a browser | Accepted · completes M8, implements ADR-0032 and PRV-18 |
| [0049](0049-network-hard-layer.md) | A link-local hard layer for network tools: catches the cloud metadata endpoint without breaking loopback-based tests or a local dev server | Accepted · adds PERM-16 |
| [0050](0050-trim-should-items-from-v1.md) | Move v1's `(Should)` items to v2 before building M9–M11: worktree-isolated subagents, sandbox backends beyond `none`, `edgar skills audit`, out-of-REPL session compaction | Accepted · moves SUB-11, PERM-15, SKL-18, CTX-10 to v2 |
| [0051](0051-controlling-edgar-from-elsewhere.md) | Controlling edgar from a phone or a remote terminal: a separate project embeds it, and the proxy relays or blocks but never answers | Accepted · constrains `edgar.run()`, amends ADR-0048 decision 1, "Never" list unchanged |
| [0052](0052-media-input-in-v2.md) | Media input in v2: one `ImageBlock` and nothing else, every other format converted by a tool at the boundary | Accepted · amends PRD §5.3 and §5.1 |
| [0053](0053-what-1-0-actually-ships.md) | What 1.0 actually ships: cut the commands that read a format, never the format itself | Accepted · moves CLI-20, TOOL-14, CTX-18, CTX-2, CFG-2, ROUTE-9 and parts of CFG-5, EXT-3 and PRV-14 to v2 |
| [0054](0054-m9-subagents-as-built.md) | M9 as built: subagents fan out through `execute_many()`, a multi-row status bar, an example agent, and `check_capabilities` wired in | Accepted · completes M9 |
| [0055](0055-m10-extensions-as-built.md) | M10 as built: a per-turn verify override mirroring the daily cap, verify authorisation moved down to `core/verify.py`, `edgar.run()` with every heavy import deferred, and the last three slash commands | Accepted · completes M10; refines ADR-0006, ADR-0041; implements EXT-9, SKL-17, VER-1 in part, CLI-14 |
| [0056](0056-m11-as-built.md) | M11 as built: Cookbook, EXTENDING, DEPENDENCIES, examples in CI, the docs-coverage test, release automation | Accepted · completes M11 and 1.0; implements NFR-10 in part |
| [0057](0057-daily-driver-before-learning.md) | The daily driver comes before learning: v2 (M18–M22) is the daily driver, v3 (M12–M15) learning, v4 (M17, M16) unattended; every milestone ends with its tour | Accepted · supersedes ADR-0015's tier contents and v2 budget; assigns ADR-0052 to M20 |
| [0058](0058-m18-the-tour-pages-and-the-map-as-built.md) | M18 as built: a tour page per v1 feature, the Core stops that were missing, a test that fails on a source file with no stop, and a generated map of the harness (tree only, no flow arrows, no JS library) | Accepted · completes M18; implements ADR-0057's tour condition; adds nothing to `src/` |
| [0059](0059-m19-working-state-as-built.md) | M19 as built: pinned working state, plan mode and the `todo` tool | Accepted · completes M19 |
| [0060](0060-m20-seeing-and-searching-as-built.md) | M20 as built: a four-field `ImageBlock`, images end to end, web search and git as zero-code extensions | Accepted · completes M20; implements ADR-0052 |
| [0061](0061-m21-isolation-as-built.md) | M21 as built: worktrees and sandboxes; the sandbox confines writes and the network, not reads | Accepted · completes M21; changes the `Sandbox` protocol |
| [0062](0062-m22-inspection-commands-as-built.md) | M22's inspection commands as built | Accepted · implements CFG-5, ROUTE-9, EXT-3, SKL-18; amends ADR-0042; defers PRV-14 |
| [0063](0063-m12-learning-foundations-as-built.md) | M12 as built: learning foundations | Accepted · implements ADR-0017 |
| [0064](0064-m13-controller-as-built.md) | M13 as built: the controller | Accepted · supersedes ADR-0008 on two points |
| [0065](0065-m14-skill-synthesis-as-built.md) | M14 as built: skill synthesis | Accepted · resolves OQ-6 |
| [0066](0066-m15-escalation-as-built.md) | M15 as built: escalation | Accepted · follows ADR-0013 |
| [0067](0067-v5-fork-governable-autonomy.md) | v5 forks onto a long-lived branch under a new name: a governable, fully autonomous agent, with amended rules on that line only; `main` stays edgar 4.x | Proposed |

## Writing a new ADR

Copy `TEMPLATE.md`. Number sequentially. An ADR is warranted when a decision is
hard to reverse, when a reasonable person would choose differently, or when you
will otherwise be asked "why is it like this" more than twice.
