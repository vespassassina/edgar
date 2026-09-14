# Journal

What was asked, what was done, what was decided and what is still open, newest
first. Decisions with alternatives worth keeping get an ADR; user-visible changes
also go in [`CHANGELOG.md`](../CHANGELOG.md); milestone state is the table at the
top of [`ROADMAP.md`](ROADMAP.md).

## Open items

Carried forward until done. Newest first.

- **There is no first-run wizard, and a fresh install has no config at all.**
  `edgar init` and `edgar doctor` are M11 and unbuilt, so today the only thing that
  ever writes config is the picker, which writes one key (`[model] default`) and
  only when no file exists — an existing config is hand-authored and never edited
  ([ADR-0034](adr/0034-model-picker.md), the same rule that protects `AGENTS.md`).
  **Desired first run:** `edgar` with nothing configured offers to set itself up
  rather than erroring; `edgar init` writes a working, commented `config.toml` with
  the choices already made (never blanks), detects credentials that are already in
  the environment or the keyring, offers sign-in for a provider that supports it,
  and never puts a secret on disk [CFG-4, CFG-6]. The model picker stays a picker:
  the wizard is the thing that writes config, and it still writes only a file that
  does not yet exist.

- **Review the capability broker design** (ADR-0039, M17) before M17 starts. The
  choices most open to argument: five caveats only; caveats only from what people
  type (no model-derived scope); no prompt on a refusal, `/scope` widens; the log
  named "receipt"; HMAC and its limit; on by default in v2; M17 before M16; about
  400 lines against v2's budget.
- **Try the REPL on a real model.** Start Ollama (`OLLAMA_CONTEXT_LENGTH=16384
  ollama serve`), then `uv run edgar --model ollama/qwen3:8b` from the repo. M4 was
  tested with the fake model and through a pseudo-terminal, not live.
- **`@path` attachments in prompts** (CLI-3) are not built; piped stdin is. M5 did
  not take them (no lines to spare); pick a milestone.
- **GitHub Copilot's gate** (ADR-0043): register edgar's OAuth app and confirm
  GitHub allows direct use of the Copilot endpoint, before M8 ships the provider.
- **Try keyless sign-in on a real cloud.** Run the Cookbook's Azure, Vertex or
  Bedrock block against a real account; the tests use a stand-in CLI only.
- **Record the remaining cassettes** with real keys: `just record-cassettes openai`
  (and azure, openrouter, anthropic). Only Ollama's are recorded so far.
- **Live smoke workflow** (TESTING.md layer 5) is specified but not created; it
  needs provider secrets in the repository settings first.
- **Size watch.** The budget test measures v1: 6,809 of 8,000 lines of code,
  1,191 left for M9 to M11. Core's own files stayed at 5,000.
- **`/skills` and `/tools` in the REPL** still say they arrive in M6, which is done;
  `edgar skills list` and `edgar tools list` exist. Wire them or relabel them.
- **A moved project loses its facts** (ADR-0045): the scope is a hash of the path.
  A re-scope command, or matching on the git remote, is open.
- **The picker's provider question has no default.** In `edgar models`, Enter at
  "provider?" cancels. A sensible default would be the first provider whose key
  is set, or Ollama if it answers; it needs a few lines of code Core does not have.
- **A skill's `verify` command** is accepted and ignored in Core; it moves to M10
  with deterministic activation (ADR-0041).
- **Which style guide?** The sensible-defaults rule went into PRD §4, CLAUDE.md and
  the `AGENTS.md` patch. If "my style guide" meant another file, name it.

## 2026-09-14 · The picker signs you in

**Asked**
- Whether `edgar models` lets you pick a model and sign in, whether it can
  configure the harness, and whether there is an initial wizard. Then: take note of
  the gaps and the desired results, and fix the small one — "that's basic usability".

**Done**
- Wrote both gaps down: this one, and the missing first-run wizard (still open,
  M11). The desired first run is now spelled out in the roadmap's M11 section
  instead of living only in a conversation.
- Fixed the first: `_offer_sign_in()` in `cli/models.py`, 24 lines of code. When the
  provider you picked has an `oauth` row in `quirks.py` and no key in the
  environment or the keyring, the picker asks "no key for openrouter. Sign in now?
  [Y/n]"; Enter runs `keys.login()` and the picker carries on to the model list with
  the key it just issued, so the no-keyring case works for this run too. `n` gives
  the old message naming the variable. Two tests in `tests/integration/test_login.py`
  cover both answers, and the existing "a missing key is named, not asked for" test
  still passes unchanged for OpenAI, which has no browser sign-in.

**Decided**
- Offering a browser here does not contradict ADR-0048's "a turn never opens a
  browser": that rule keeps browsers out of an automated turn, where nobody is
  watching. `edgar models` is a human sitting at a prompt. Noted in ADR-0048.
- Enter is yes, per the sensible-defaults rule. The picker still never asks anyone
  to type a key, which was the original reason it refused to help at all.

**Pending**
- The first-run wizard (`edgar init`, `edgar doctor`) is still M11 and unbuilt.
- v1 is at 6,833 of 8,000 lines of code.

## 2026-09-14 · 0.1.0 on PyPI

**Asked**
- "lets do pypi and gh": cut the 0.1 release.

**Done**
- Version 0.1.0 in `pyproject.toml` and `src/edgar/__init__.py`; "Unreleased"
  moved under `## 0.1.0 — 2026-09-14` in the changelog; the roadmap's "Shipped in"
  column now says 0.1.0 for M1 to M8; README says 0.1 is on PyPI and installs with
  `uv tool install edgar-harness` instead of from the repository.
- Tagged `v0.1.0` and published the GitHub release, which triggers
  `.github/workflows/release.yml`: the offline suite, `uv build`, then trusted
  publishing to PyPI with build attestations and no API token anywhere [NFR-14].

**Decided**
- 0.1 is cut from `main` (M0 to M8), not from `f89e35b` (Core alone). The maintainer
  chose the release people can actually use over the one that matches the tier
  story: 6,809 lines of code, with memory, forks, MCP and signing in included. The
  roadmap's tiers are unchanged — 1.0 is still where v1's extension formats freeze —
  so `f89e35b` no longer matters and the `release/0.1` branch idea is dropped.
- Marked a full release, not a pre-release: 0.0.1 and 0.0.2 were skeletons, this is
  a harness, and it should be what `uvx edgar-harness` gives people.

**Verified**
- `release.yml` went green and PyPI now lists 0.1.0 as latest. Both
  `uvx --from edgar-harness==0.1.0 edgar --version` and the same with
  `edgar-harness[keyring]` install from PyPI and print `edgar 0.1.0` (macOS; the
  extra pulls 5 more packages). The wheel was also smoke-tested in an empty venv
  before the tag.

**Pending**
- Try the published release on Windows and Linux, and sign in for real once
  (`edgar login openrouter`) now that the keyring extra installs from PyPI.

## 2026-09-14 · M8 done: signing in

**Asked**
- Build M8 (second half).

**Done**
- `auth/`, 317 lines of code: `oauth.py` (PKCE, a loopback listener on a port the
  OS picks, the browser visit, the form or JSON POSTs), `store.py` (the OS keyring
  through the optional `keyring` extra, every secret registered with `scrub()` as
  it is written or read), `keys.py` (`edgar login PROVIDER`) and `mcp.py` (a
  remote MCP server's own sign-in) [PRV-18, CFG-6, ADR-0032].
- `edgar login openrouter` / `edgar logout NAME`: the browser flow, the exchange,
  the keyring; with no keyring the key is printed once and stored nowhere. The
  provider's own shape (a `callback_url` parameter, a JSON body, a `key` field) is
  an `OAuth` row in `quirks.py`, so a second provider is a row. `connect()` reads
  the keyring after the environment, and its error names `edgar login NAME`;
  `edgar models list` says which providers are signed in.
- `edgar mcp login NAME` / `edgar mcp logout NAME`: RFC 9728 protected-resource
  metadata, RFC 8414 authorization-server metadata, RFC 7591 dynamic client
  registration with the exact loopback redirect, the code exchange with an RFC
  8707 `resource`, and a refresh when the stored token has run out. The transport
  sends `Authorization: Bearer …` when a token is stored, and a 401 becomes a tool
  failure saying `edgar mcp login NAME`.
- `keyring>=25` as an optional extra in `pyproject.toml`; nothing on the startup
  path imports it (NFR-1).
- Tests: 10 in `tests/integration/test_login.py`, with no browser and no network —
  the keyring is a dictionary, the "browser" is a loopback client the test drives,
  and every HTTP exchange is a function the test supplies. One of them plants a
  token in the keyring and checks it never reaches anything edgar prints.

**Decided** (ADR-0048)
- The loopback port is opened *before* the authorization URL is built, because
  dynamic client registration must declare the exact redirect URI.
- edgar registers itself as a public client (`token_endpoint_auth_method: "none"`,
  PKCE as the only proof) rather than shipping a client id it could not keep
  secret; a server that registers none says to ask its operator.
- A turn never opens a browser: sign-in is a command a human runs.
- Tokens live in the OS keyring and nowhere else — no token file — and are
  registered for redaction when read back, not only when written.

**Pending**
- GitHub Copilot [PRV-19, ADR-0043] stays gated on GitHub's terms.
- `tests/integration/test_forks.py::test_fork_and_load_on_the_command_line` failed
  once during a `just check` run and passed on four full runs after it. Watch it;
  if it comes back, it is a real race and not a flake.
- 0.1 still waits on the maintainer; `f89e35b` stays the Core-only commit.

## 2026-09-14 · M8a: MCP servers, deferred schemas and /browser

**Asked**
- Build M8.

**Done**
- `tools/mcp/`: the stdio transport (a child process, one JSON-RPC message to the
  line, `ping` answered and every other server-initiated method refused) and the
  Streamable HTTP one (JSON or SSE answers, `Mcp-Session-Id`,
  `MCP-Protocol-Version` after the handshake), protocol `2025-06-18` [TOOL-7].
- `Server` starts nothing at session start: its tool list comes from a new
  `mcp_tools` table in `~/.edgar/edgar.db`, keyed by a sha256 of its config block,
  and the process starts on the first call [TOOL-8]. `close()` stops what started.
- `mcp__server__tool` naming, collision order builtins → extra → MCP → user →
  project with a warning [TOOL-9]; results always untrusted, local servers in the
  `shell` category and remote ones in `network`, and the annotations a server
  publishes shown by `edgar mcp list` but never read by `decide()` [TOOL-13].
- `tool_search` [TOOL-15]: when the schemas pass `tools.schema_budget` (4,000 by
  default) the MCP ones are deferred, `tool_search`'s own description lists them by
  name and a line, and a search loads the matches' full schemas for the rest of the
  session. It also starts a server no session has run yet, and remembers its tools.
- `[mcp.NAME]` config blocks (not the Blueprint's `[[mcp.servers]]`), `${env:NAME}`
  expanded at spawn time and scrubbed from every result; project servers need
  `edgar trust` [PERM-13]; `edgar mcp list|test NAME`.
- `/browser` [CLI-29]: `[browser] tool = "..."` names a tool you already have,
  `[browser] command = ...` an MCP server started only when you type `/browser`,
  and with no block it prints the two blocks you could write. It never picks one.
- Tests: 13 in `tests/integration/test_mcp.py` against a real stdio server
  (`tests/support/mcp_server.py`) and an httpx `MockTransport` HTTP one, two REPL
  tests for `/browser`, and an e2e run with five servers configured that starts
  none of them. 617 lines of code; v1 is at 6,419 of 8,000.

**Decided** (ADR-0047)
- `[mcp.NAME]` tables, so layered config merges server by server and key by key.
- A config-hashed tool cache plus `tool_search` resolves TOOL-8 against needing
  names up front: a session starts no server, ever, and a cold one is started by
  the search or by `edgar mcp list`.
- The deferred listing lives in `tool_search`'s description, not in the prompt
  builder, and a deferred tool is still callable by name.
- Streamable HTTP only; the deprecated HTTP+SSE transport is not supported.

**Pending**
- M8b: OAuth 2.1 with PKCE for remote servers and `edgar login PROVIDER` /
  `edgar logout` (OpenRouter first), tokens in the keyring [ADR-0032, PRV-18].
  Copilot [PRV-19] stays gated on its terms.
- 0.1 still waits on the maintainer; `f89e35b` stays the Core-only commit.

## 2026-09-14 · M7 done: forks, saved sessions and the daily cap

**Asked**
- Keep building: the rest of M7.

**Done**
- Session forks [CLI-22]: `/fork [N]` and `edgar --fork ID[@TURN]`. A fork is a
  new file whose second line names its parent and turn; `chain()` in
  `storage/transcript.py` reads parents up and back down, so forks of forks work
  and nothing is copied. `edgar sessions rm` refuses a session with forks.
- `/save [PATH]` writes the chain as one file, spilled output inlined and every
  string redacted; `/load PATH` and `edgar --load PATH` copy it into a new session
  here and open it the way `--resume` does. `/history` shows the whole
  conversation from the record [CLI-25].
- The daily cap [BUD-2]: a `spend` table in `~/.edgar/edgar.db` records each
  top-level turn with a known cost; before each turn, what is left of
  `daily_cost_cap` becomes the turn's cap, and with nothing left the turn does not
  start (exit 6). `core/loop.py` is unchanged. `edgar cost` shows today and the
  last seven days; `/cost` adds today [BUD-6].
- A bug found by the new tests and fixed before commit: redaction skipped tool
  result text in `/save`, because `asdict` keeps tuples.
- 11 tests in `tests/integration/test_forks.py` and one more REPL test; the REPL's
  `/save`, `/history` and `/load` expectations updated. 176 lines of code. ADR-0046;
  the tour's session stop and size table updated; M7 marked done in the roadmap.

**Decided** (ADR-0046)
- A fork points at its parent rather than copying it; turns are counted by
  `TurnFinished`, undone ones included.
- A saved file is the resolved chain, blobs inlined, redacted string by string;
  loading one makes a new session of this project.
- The day's spend is one table per user; the daily cap works through the turn cap,
  so unknown pricing stops a capped turn after one request, as the other caps do.

**Pending**
- M8 (MCP) is next. 0.1 still waits on the maintainer; `f89e35b` stays the
  Core-only commit to cut it from.

## 2026-09-14 · M7 begins: facts, recall and session search

**Asked**
- Keep building: M7, memory and session search.

**Done**
- `memory/store.py`: facts in `~/.edgar/memory.db` with scope, provenance,
  confidence and status (pending, active, superseded, forgotten), an undo log by
  operation, contradiction detection by word overlap [MEM-10] and a per-scope cap
  with eviction [MEM-11]. `memory/redact.py` redacts every fact and indexed turn.
- `memory/recall.py` and `memory/retriever.py`: the `Retriever` port and its
  `fts5` adapter, porter and trigram indexes over active facts and past sessions'
  user and assistant text, indexed lazily at recall time [MEM-20, MEM-24].
- The pinned set: chosen once in `setup()`, project facts first, at most
  `[memory] pinned_max`, placed between the instruction files and the skill index
  as notes with a capacity header [MEM-6, MEM-7].
- The `remember` tool proposes (pending); the REPL asks `save? [y/N]` at the end
  of the turn, and Enter forgets; `-p` leaves proposals for `edgar memory review`
  [MEM-21]. The `recall` tool searches facts, sessions or both.
- `/remember TEXT` and `/memory` in the REPL; `edgar memory
  list|add|edit|review|forget|undo`, with `edit` as a markdown round trip in
  `$VISUAL` or `$EDITOR` [MEM-4, MEM-5, MEM-23].
- `[memory]` in config (`pinned_max`, `scope_cap`, `retriever`, `autolearn`); the
  `FactProposed` and `FactSaved` events.
- 13 unit tests (`tests/unit/test_memory.py`) and 4 integration tests
  (`tests/integration/test_remembering.py`): a fact typed in one session is in the
  next session's prompt and not in its own, a yes saves a proposal, a no keeps it
  out of every prompt and every recall, and `-p` plus `edgar memory review`.
- The budget test moved to the v1 tier. ADR-0045; the tour's stop 20 is now a
  built stop and the size table has a `memory/` row.

**Decided** (ADR-0045)
- One database for the user, not one per project, so global facts follow the
  user and one index covers both scopes.
- A fact's text never changes; every change is a status change under an
  operation number, so undo always works, and the index holds exactly the active
  facts.
- Contradiction is word overlap of at least half, not a model call: no hidden
  model, at the price of missing opposites written in different words.
- `remember` needs no permission prompt outside read-only mode; the question at
  the end of the turn is the gate. A no forgets rather than deletes.
- `recall` output is framed as notes, not instructions, and does not taint the
  session.

**Pending**
- The rest of M7 (forks, `/save`, `--load`, `/history`, the daily cap, `edgar
  cost`).
- 0.1 is still waiting; cut it from `f89e35b` if Core alone should ship.

## 2026-09-14 · Keyless sign-in for Azure, Google and AWS

**Asked**
- Sign in to the models on Azure, AWS and Google Cloud with OAuth where they
  support it, not only keys, because Azure is phasing keys out.

**Done**
- Checked the three clouds. Azure OpenAI takes an Entra ID token as bearer, and
  organisations can switch keys off. Vertex AI's OpenAI-compatible endpoint takes
  a Google access token. Bedrock's OpenAI-compatible endpoint takes a short-term
  API key minted from the AWS identity by AWS's token generator. All three end in
  a bearer token that the cloud's own CLI can print.
- Built `api_key_command` [PRV-20] in Core: an argv in a `[providers.NAME]` block
  of user config. It runs when the provider resolves if no key is set, and its
  output goes as `Authorization: Bearer`, so Azure switches from its `api-key`
  header. It runs again for any request once the token is ten minutes old. It
  runs without a shell (`shutil.which` finds `az.cmd` on Windows). A failure
  quotes the command's stderr with a hint to sign in. A project config that
  names it fails to load.
- Eight tests in `tests/unit/test_provider_sign_in.py`, with a stand-in CLI run
  by `sys.executable`. The token is kept out of `repr`, and a test checks that
  no event carries it.
- ADR-0044, PRV-20, CFG-6 amended, the Blueprint's §5.2, a Cookbook recipe with
  blocks for Azure, Vertex AI and Bedrock, the README's "Any model" line, the
  CHANGELOG, and the tour's providers stop.

**Decided** (ADR-0044)
- A command the user names, not OAuth written into edgar and not the clouds'
  SDKs. The CLIs already handle sign-in, MFA, SSO and refresh. Writing it
  ourselves would need a client id per cloud, or borrowing theirs; the SDKs
  break the import and dependency budgets.
- User config only, because provider resolution comes before `edgar trust`.
- Bedrock via its bearer API key; SigV4 is left to a plugin if ever needed.
  Claude on Bedrock's or Vertex's own Anthropic routes is out of scope.
- Core had 34 lines of code to spare and this took 35. The endpoint hint in
  `connect` went to one line, so Core is at exactly 5,000.

**Pending**
- Try it against a real Azure, Vertex or Bedrock account.
- The 0.1 release still waits on the maintainer's yes, and it would now
  include this.

## 2026-09-14 · GitHub Copilot as a provider, planned for v1

**Asked**
- Add GitHub Copilot as a provider: a subscription gives access to many models,
  with OAuth to sign in.

**Done**
- Checked GitHub's position. It supports Copilot subscriptions in OpenCode
  through a named partnership (device login), and its Copilot SDK (GA) lets any
  app use a user's subscription through the app's own OAuth app. Direct use of
  the Copilot model endpoint is documented for no third party but OpenCode.
- Specified it, nothing built: ADR-0043, PRV-19 (v1, *Should*), PRD §5.2's
  non-goal and PRV-18 now name the exception, a bullet under M8 in the roadmap,
  the Blueprint's §5.2, and a pointer in ADR-0032's status line.

**Decided** (ADR-0043, the maintainer chose option A)
- Direct endpoint, not the SDK: the SDK runs Copilot's own agent loop, which
  would drive edgar's tools outside its permissions and verify gate.
- The device flow uses edgar's own registered OAuth app, never a borrowed
  client id; the token goes to the keyring; the provider is one `quirks.py` row.
- It lands in M8 with `edgar login`, about 80 lines of code against v1.
- Every other subscription is still never; each exception needs its own ADR
  citing the vendor's documentation.

**Pending**
- **Gate before shipping:** the maintainer registers the OAuth app on their
  GitHub account and confirms with GitHub's terms, or GitHub itself, that a
  registered app may call the Copilot endpoint directly. If not, the ADR is
  superseded by the SDK route or dropped.
- How `/cost` shows premium-request multipliers.

## 2026-09-14 · A skill audit, planned for v1

**Asked**
- A feature for later: edgar should judge a skill before it is installed (its
  quality, its dangers, how it is written) and suggest changes that bring it up
  to a strict standard.

**Done**
- Specified it, nothing built: SKL-18 in the PRD (v1, *Should*), EXT-3 now audits
  before copying, a bullet under M10 in the roadmap, `skills/audit.py` in the
  Blueprint's module map and §6.6, a sentence in the tour's stop 23, and
  ADR-0042.

**Decided** (ADR-0042)
- `edgar skills audit PATH|GIT_URL`: conformance to a written standard (rule IDs
  `SA-n`, `--strict` for SKL-16's body shape) and dangers, all deterministic.
  These alone set the exit code and the default answer in `ext add`.
- `--review` is opt-in: the configured model reads the skill as untrusted data,
  with no tools, and only advises. A hostile skill can aim an injection at its
  reviewer, so the model's opinion never clears a finding.
- `--diff` prints suggested fixes to stdout and writes nothing.
- It lands in M10, with `ext add` (the moment a skill is copied in) and SKL-17's
  description lint. About 200 lines of code against v1's budget.

**Pending**
- Write the standard's rule list (`SA-1`…) when M10 starts; the ADR names its
  contents but not each rule.

## 2026-09-14 · M6: skills

**Asked**
- "next item in harness": M6, skills and the Core release.

**Done**
- Skills: `skills/discovery.py` finds `SKILL.md` folders in four scopes and reads
  their frontmatter only (PyYAML, imported lazily); `context/builder.py` adds one
  index line per skill to the end of the pinned prefix; `tools/builtin/skill.py`
  loads a body on request, naming its folder so bundled files can be found. The
  tool is registered only when a skill exists.
- `edgar skills list|validate` and `edgar tools list|describe` (`cli/admin.py`,
  sharing `toolset()` with session setup, so the listing is what a session gets).
- `examples/` (a command tool, an HTTP tool, a skill), `docs/COOKBOOK.md` and a
  README quick start. `test_skills.py` and the e2e journey J9 load every example,
  so the recipes cannot drift. J3 now checks stdout holds only the answer.
- `edgar models` saves to user config on Enter (the sensible-defaults rule).
- The tour: stop 19 is built, as a sixth Core stage, "The know-how".
- ADR-0041; PRD §5.1, BLUEPRINT §6.6 and the ROADMAP updated. Core is 4,966 of
  5,000 lines of code; 479 tests pass.

**Decided** (ADR-0041)
- The tool is the loader; no `skills/loader.py`.
- Anything a human wrote beats anything learned, whatever the scope.
- A skill's `verify` command moves to v1: it would need authorising mid-turn.
- Only the four scopes that can hold a skill today; bundled and extension scopes
  come later.
- No trust gate for skills: they are instructions, and `.edgar/skills/**` is
  already a control file.

**Pending**
- The 0.1 release, on the maintainer's yes. The picker's provider default. See
  the open items.

## 2026-09-14 · The tour in artifactkit, on a midnight theme

**Asked**
- The tour must be HTML, published on GitHub as HTML, and linked from the repo's
  docs so a reader can just click. Use the maintainer's HTML style guide, with a
  dark, desaturated midnight-blue background.

**Done**
- Restyled `docs/tour/index.html` with artifactkit (the maintainer's kit): page
  head, sticky contents, section heads with status pills, stops as exhibits, a
  stepper for the five stages that marks a stage done when its stops are read, the
  size table as an `ak-table` with its source line, print rules. The three
  stylesheets are vendored in `docs/tour/artifactkit/`; only the theme block differs
  (`--t-bg:#121826`). Mermaid is themed from the same tokens and loads as the UMD
  build.
- Fixed a rendering bug: Mermaid read the turn diagram's "1. record the prompt"
  labels as Markdown lists and drew "Unsupported markdown: list". Steps are now
  written "1 · …"; `test_tour.py` checks for it and that the page's own files exist.
- Every doc link to the tour now opens the published page
  (<https://vespassassina.github.io/edgar/>), not the HTML source: README (a line
  under the headline, plus the Documentation table), BLUEPRINT, ROADMAP, TESTING and
  CLAUDE.md. The repository description ends with "Take the tour" and the address.
- ADR-0040 amended.
- The maintainer applied `docs/proposals/AGENTS.md.patch` by hand during this
  session; it went out in this commit, and the patch file and `docs/proposals/` are
  removed. CLAUDE.md and ADR-0040 no longer call it pending.

**Decided**
- The kit's stylesheets are linked, not inlined: it is a hosted page, and the
  source stays readable. artifactkit's single-file validator therefore reports the
  linked files, the Mermaid script and the raw storage keys; accepted for Pages.

## 2026-09-14 · Written to be read, and A Tour of the Harness

**Asked**
- Add granular comments, close to pseudocode, to `core/loop.py`, `core/message.py`
  and `core/events.py`. From now on, add them to any code file touched. Prefer
  shallow functions and avoid recursion.
- "Lines" always means lines of code, and comments do not count: the 5,000 limit is
  Core's code without comments. Say so in the docs and the checks.
- Write a step-by-step reading guide, a tour of the harness, with diagrams and
  sections that point at the files on GitHub, and keep it in sync. Base it on the
  maintainer's own reading guide (`OneDrive/Writing/projects/edgar/`).
- Make it HTML, split into Core, v1 and v2 so it can be read a tier at a time,
  publish it on GitHub, link it from the repository's description, and call it "A
  Tour of the Harness".
- Add to the docs and the style guide: always propose sensible defaults (Enter
  accepts about 90% of the time) and preconfigured config files when installing and
  deploying.

**Done**
- `core/loop.py`: a pseudocode header, and `run_turn` as ten numbered steps over
  five shallow helpers and a `_Turn` dataclass. Behaviour is unchanged. `core/message.py`
  and `core/events.py`: an example transcript, the pairing rule, the bus diagram,
  the order of a turn's events, and who emits each event.
- `tests/support/budget.py`: the loop counted in lines of code like everything
  else; `broker` added to the v2 paths. Budget tests rewritten: comments in the loop
  are free, code is not.
- [ADR-0040](adr/0040-written-to-be-read.md). PRD §4 gains principles 11 (sensible
  defaults) and 12 (written to be read); NFR-3 and NFR-4 define a line of code.
  README, BLUEPRINT, TESTING, ROADMAP and CLAUDE.md say "lines of code".
- [A Tour of the Harness](tour/index.html): 18 built stops in five stages, the M6
  skills stop, five v1 stops and six v2 stops marked planned with their milestone.
  Five diagrams, checked against the code: the layer map, the turn (numbered like
  `run_turn`), the bus, the tool pipeline, the permission decision and compaction,
  plus one showing where v1 plugs in and one showing where v2 attaches. A per-reader
  "read" box and a reading clock, kept in the browser.
  `.github/workflows/tour.yml` publishes it to <https://vespassassina.github.io/edgar/>;
  the repository's website link points there. `tests/unit/test_tour.py` keeps it
  honest.
- The `AGENTS.md` patch moved into the repository, at
  `docs/proposals/AGENTS.md.patch`, and gained the new comment, function and
  defaults rules, "LOC" for the loop, and `edgar.broker` in tier isolation.

**Decided**
- Every limit is lines of code; the loop's physical-line limit is gone (ADR-0040).
- Narration goes in `#` comments, not docstrings, because docstrings count.
- The tour is hand-written HTML with fixed hooks a test reads, not a generated
  file. It replaces the planned `docs/TOUR.md` (M11).
- Diagrams corrected against the code: a denied, invalid or unknown call still ends
  as a `ToolResultBlock`; `decide` checks yolo right after catastrophic commands and
  before credential paths; an `Ask` with nobody to answer becomes a `Deny` with
  `needed_prompt`.
- Left out of the tour from the maintainer's guide: the article, the broker
  decision notes and the reading log, which are personal.

**Pending**
- The shallow-helper split cost 19 lines of Core; M6 has about 175.
- ~~Apply `docs/proposals/AGENTS.md.patch`.~~ Applied by the maintainer the same day.

## 2026-09-14 · Capability broker added to v2 (spec only)

**Asked:** add to the features the capability broker we had been discussing, for
v2. The notes were the maintainer's prototype in
`OneDrive/ClaudeCode/capability-broker/` (0.0.1, 2026-09-02: intent, capability
and provenance, the ceiling and the ticket, eleven invariants, five open
questions).

**Done**
- [ADR-0039](adr/0039-capability-broker.md): the prototype mapped onto edgar.
- PRD: a v2 scope bullet, a `Broker` row in the requirement map, §7.16 with
  CAP-1..10, `/scope` and `--scope` in the CLI row, `edgar receipt` in §9.1,
  `receipt.jsonl` and `~/.edgar/receipt.key` in §9.5, `edgar.broker` in NFR-12.
- Blueprint: `broker/` in §1 and §2, `ScopeRefused` in §3.2, the `pre_tool` stage
  as hooks plus in-process vetoes in §6.2 and §6.7, a new §7.6, notes in §9 and
  §12.
- Roadmap: eighteen milestones, v2 is M12–M17, a new M17 built after M15 and before
  M16; M16 gains scheduled-run tickets.
- TESTING.md: broker property tests; `edgar.broker` in the tier-isolation list, and
  in `tests/unit/test_architecture.py` so the rule already holds. README and
  CLAUDE.md follow.

**Decided** (all in ADR-0039)
- Enforce in the tool pipeline, not with bound handles: tool schemas sit above the
  cache breakpoint and cannot change per task (CTX-17).
- Intents only from typed text, the MEM-8 source; subagent tasks, `/steer` and
  `schedule_self` refine an intent and never start one. That answers the
  prototype's "injected intent" question.
- Five caveats (`tools`, `paths`, `hosts`, `calls`, `until`); `shell` refused under
  a `paths` or `hosts` scope unless named.
- A veto only, never a prompt; the human widens with `/scope`.
- The signed log is called the receipt, since "provenance" already names config
  and fact origins. HMAC-SHA256 with a user-only key: tamper-evident against the
  agent, not against the user.
- No daemon, service, policy language or Ed25519: the Never list and NFR-5.

**Pending:** the maintainer's review of the design (open items). No code for the
broker until M17.

## 2026-09-13 · M5 done: context and sessions

**Asked:** start M5.

**Done**
- `storage/transcript.py`: the JSONL record in `.edgar/sessions/` (git-ignored),
  replay, `find` by id or unique prefix, the listing. `--resume [ID]`,
  `--continue`, `edgar sessions list|show|rm`.
- `context/compact.py`: S1 elide, S2 fold into one summary (the compactor model,
  or the main one), S3 only past the window, `ContextOverflow` with a hint; every
  stage recorded and replayed by position. Runs before every request, so it
  compacts inside a long tool-calling turn too. `/compact [FOCUS]`.
- `context/builder.py`: personality and instruction files (project, then
  `~/.edgar/`) read once and joined to the system prompt; `edgar prompt show`
  includes the personality.
- Session commands `/new /clear /reset /undo [N] /retry /title /sessions /load ID`,
  each an appended record. The REPL prints the conversation on resume.
- Turn and session cost caps: reason `budget_exceeded`, `-p` exits 6.
- The control-file check: digests at session start and end, a `control` record,
  a warning in the next session.
- Tests: a 200-turn session on a 6,000-token window compacts over and over (mostly
  S1), with the pairing invariant and an unchanged prefix on every request, and
  replays to the exact view; a 40-call turn compacts inside itself; overflow;
  caps; resume; `/undo 2` then replay; property tests for every stage. 419 tests
  in about 6 s.

**Decided**
- [ADR-0038](adr/0038-context-and-sessions-as-built.md): records address the view
  by position (`upto`); S3 only past the window, and CTX-8 reworded to match; the
  output reserve is at most half the window; a cap is a turn reason, not an
  exception, and unknown price counts as over; the control check compares within
  a session; block kinds are class names.
- Size: M5 as specified left 126 lines for M6. Collapsing trailing-comma splits gave
  17; `/history` and `edgar cost` moved to M7, `edgar context show` to M11.
  Core 4,806.
- CTX-10 (`edgar sessions compact`, a Should) not built; it stays in M11.

**Next:** M6, skills and the Core release (0.1, ask first).

## 2026-09-13 · Review for size; four features to v1

**Asked:** a quick review to shave and simplify, then follow the recommendation;
"core stays core, 5k limit".

**Done**
- Review: Anthropic became a row in the quirks table, with one `connect()` for
  endpoint and key checks (both adapters lost their `make()`); the fake
  provider's scripting moved to `tests/support/scripted.py`; `read` and `ls` use
  the shared schema helper. 116 lines out, 4,415 → 4,299, all 388 tests green.
- Moved to v1: plan mode and `todo` (M9), `/save` `/load` `edgar --load` and the
  daily cost cap (M7), `edgar login` (M8, with MCP OAuth).

**Decided**
- [ADR-0037](adr/0037-core-fits-in-5000.md): Core stays under 5,000 lines;
  simplify first, then move whole features.

**Next:** M5.

## 2026-09-13 · M3 done: tools, permissions, the verify gate

**Asked:** start M3.

**Done**
- `permissions/`: a pure `decide()` over a `Policy`, the mode table from the
  Blueprint cell by cell, rules, exact grants in `.edgar/edgar.db`, taint, control
  files, credentials, and hostile paths resolved before matching. The guard asks
  in the REPL (answer with the next line: once, session, always, no) and denies
  with `-p`, which then exits 5. 100% branch coverage.
- Built-ins `write`, `edit`, `glob`, `grep`, `shell`, `fetch`; processes are killed
  as a group on cancel or timeout.
- Command and HTTP tools from `.edgar/tools/*.toml` and `~/.edgar/tools/`,
  project over user over built-in with a warning; project trust with
  `edgar trust` and `--no-project-exec`.
- The verify gate (`--verify`, `[verify] command`): authorised before the turn,
  run when the model stops after a non-read tool, feedback on failure, exit 9
  when exhausted.
- yolo only through `EDGAR_YOLO=1` or a typed confirmation.
- 388 tests in about 5.5 s.

**Decided**
- [ADR-0036](adr/0036-safety-layer-as-built.md): outside the working directory
  asks rather than denies; the audit trail is the event stream until M5; `/browser`
  moves to M8 and the control-file hash warning to M5.

**Budget.** M3 took about 1,060 lines against a target of 800. Core is at 4,415 of
5,000, with 585 left for M5 (context, compaction, sessions, session commands,
personality, cost caps, plan and todo) and M6 (skills, `edgar login`, release).
They will not both fit. Candidates for v1, by how separable they are: `/save` and
`/load` with `edgar --load`; plan mode and the `todo` tool; the daily cost cap;
`edgar login`; skills. Alternatively the Core budget is raised by an ADR, which
the roadmap says it should not be.

**Next:** the maintainer decides what moves; then M5.

## 2026-09-13 · M4 done: the REPL

**Asked:** start M4 (the interactive shell and model picker, per the replan).

**Done**
- `edgar` on a terminal opens the REPL: a prompt that stays open while a turn runs,
  text streamed a line at a time above it, and the status line as its toolbar.
  Plain text queues, `/steer` lands at the loop's safe point, `/btw` answers on the
  side without touching the transcript, `/stop` and Ctrl-C cancel (twice exits),
  `/pause` and `/resume` hold at the safe point. Also `/status /model /mode
  /thinking /queue /cost /title /new /clear /help /quit`; commands that need later
  milestones say which.
- Cancellation seals the transcript (`core/cancel.py`): unanswered calls get
  "cancelled by user", streamed text is kept marked interrupted. A property test
  cancels at generated moments and checks the pairing invariant every time.
- `edgar models` and `/model` pick a provider, then one of its models, fetched
  from that provider only when asked; `edgar models` writes the default into a new
  config file, never an existing one.
- `-p`: `--json`, `--events`, `--quiet`, `--show-thinking`, `--no-color`; piped
  stdin attached as context; a status line on stderr; Ctrl-C exits 7.
- 329 tests in about 4.5 s. The REPL was also driven through a pseudo-terminal
  against the fake model.

**Decided**
- [ADR-0035](adr/0035-repl-as-built.md): prompt_toolkit owns the bottom of the
  screen, text streams a line at a time, no Markdown rendering, and `rich` is
  dropped from the dependencies; the REPL's logic is a plain `Shell` class.

**Next:** M3, tools, permissions, the verify gate, and CLI/HTTP tools.

## 2026-09-13 · M2 done; first real model; replan

**Asked**
- Start M2 (real providers).
- "I don't have credits on the Anthropic API key. Can we use my subscription?"
- edgar works on Ollama; how to stop Ollama.
- Plan for OAuth; an interactive shell; an edgar model picker for choosing and
  configuring models; keep track of everything we do.
- "We need API + CLI soon; 3,000 tokens for the MCP is too much."

**Done**
- M2, commit `ff4db71`: `openai_compat.py` with the quirks table (OpenAI, Azure,
  OpenRouter, Ollama, any `[providers.NAME]`), `anthropic.py`, shared `http.py`
  (retries, SSE, error mapping, token counts), `repair.py`, `pricing.py`,
  `routing.py`, prompt profiles with `compact.md`, `[providers.*]` and
  `[pricing.*]` config, `edgar models list`. CI green on all nine jobs.
- Contract suite over six providers (offline in about 2 s), a loopback fixture
  server for user-defined providers, cassette record and replay, 290 tests in
  total.
- **First live model run:** the Ollama contract suite passed live against
  `qwen3:8b` on the maintainer's Mac (15 recordable tests), and Ollama's cassettes
  are now recorded exchanges rather than synthetic ones. Recording found a flaw:
  tests sharing a scenario overwrote each other's recording. Fixed: the first test
  to use a scenario owns its recording.
- Subscriptions answered: not possible, by Anthropic's terms and by edgar's own
  recorded decision. Free ways to test were given instead: Ollama (used), OpenRouter
  `:free` models, Gemini's free tier through a config block.
- Tracking started: this journal, `CHANGELOG.md`, a status table in the roadmap,
  and the rule in `CLAUDE.md`.

**Decided** (the maintainer chose each, 2026-09-13)
- [ADR-0031](adr/0031-provider-layer-as-built.md): how the provider layer was
  built where the Blueprint sketch left room: tool support learned from the first
  refusal, no reasoning replay over Chat Completions, synthetic cassettes until
  recorded, OQ-3 resolved.
- [ADR-0032](adr/0032-oauth-keys-and-mcp.md): OAuth only to issue API keys
  (`edgar login`, OpenRouter first, M6) and for remote MCP servers (moved from v2 to
  M8). Never for subscriptions, now also a PRD non-goal.
- [ADR-0033](adr/0033-replan-after-m2.md): M4 (the REPL) comes next, before M3.
  Command tools and HTTP tools (the "CLI + API" alternative to MCP) move from M6
  to M3 along with project trust; `/browser` can point at a browser CLI.
- [ADR-0034](adr/0034-model-picker.md): `edgar models` and `/model` become an
  interactive picker that lists a provider's models only on request, and creates
  a config but never edits one.

**Next:** M4, the REPL.

## 2026-09-13 · M0 and M1; spec additions

**Asked**
- Start building Core; connect the GitHub repository; choose a licence; publish to
  PyPI.
- What the invariant is; a block diagram in the README.
- Input during a turn: `/queue` (the default), `/steer`, `/btw`.
- Session commands: `/new /reset /clear /history /save /retry /undo N /title /stop
  /pause /resume /plan /status /sessions /model /init /load /browser`, and a
  `personality.md` file.

**Done**
- M0: the package skeleton, CI on {ubuntu, macos, windows} × {3.12, 3.13},
  trusted publishing. Released as `edgar-harness` 0.0.1 and 0.0.2 (0.0.2 adds the
  `edgar-harness` command so `uvx edgar-harness` works).
- M1, commit `2c25162`: messages and the pairing invariant, the event bus, the
  loop, the fake provider, `read` and `ls`, the tool pipeline with spill, the
  deny-by-default policy, the prompt file, layered config with provenance.
- The README block diagram; spec updates for input during a turn, session commands
  and the personality file (commit `c6ec5a1`).

**Decided**
- [ADR-0026](adr/0026-licence-agpl.md): AGPL-3.0-or-later.
- [ADR-0027](adr/0027-distribution-name.md): distributed as `edgar-harness`
  (the name `edgar` was taken on PyPI); the command stays `edgar`.
- [ADR-0028](adr/0028-input-during-a-turn.md): plain text queues, `/steer` lands at
  the loop's one safe point, `/btw` runs outside the transcript.
- [ADR-0029](adr/0029-session-commands.md): session commands append records and
  never rewrite; `/undo` rewinds the conversation, not the disk (OQ-10); titles
  never use a model.
- [ADR-0030](adr/0030-personality-file.md): `personality.md`, the project file
  replacing the user one; tone only, never permissions.
