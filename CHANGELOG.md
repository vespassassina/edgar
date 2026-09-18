# Changelog

What changed for people using edgar, newest first. The reasons live in
[`docs/adr/`](docs/adr/), the day-by-day record in [`docs/JOURNAL.md`](docs/JOURNAL.md).
Versions follow the tiers in [`docs/ROADMAP.md`](docs/ROADMAP.md): 0.0.x while
Core was being built, 0.1 the first release you can work in, 1.0 when v1's
extension formats freeze.

## Unreleased

### Added
- **The controller, off until you turn it on (v3, M13).** After a turn ends, five
  deterministic checks look at how full the context got, how many turns in a row
  ended with a failing tool call, how much of today's cost cap is gone, how much
  the model wrote and how long it took. If none of them trips, nothing happens —
  no call, no cost, no wait. If one does, edgar asks a second model, **with no
  tools at all**, and that model may ask for exactly eight things: compact
  earlier, switch to a model you already configured, tighten a permission, warn
  you, stop acting, propose an instruction, propose a skill, or do nothing. It
  cannot loosen a permission, pick a model you never named, write your
  instructions file, or save anything to memory. Set `[controller] enabled =
  true` to switch it on; `mode = "always"` looks at every turn
  [CTRL-1..CTRL-12, ROUTE-8, ADR-0008, ADR-0064].
- **Everything it does is a dry run first, and revertible.** `compact` and
  `switch_model` outlive the session, so they are logged as "would have" until
  you say otherwise. **`edgar controller log`** shows what it did, what it would
  have done and what it was refused, newest first; **`edgar controller apply ID`**
  turns one into the real thing; **`edgar controller revert ID`** takes one back
  out. What edgar is running under is derived from that log, so the log and the
  live state cannot disagree [CTRL-6, CTRL-7, CTRL-10].
- **A proposed instruction is a file you read, never an edit you did not make.**
  `propose_instruction` and `propose_skill` write Markdown into
  `.edgar/proposals/`, named after their own log row, and stop there. edgar does
  not write your instructions file and does not know its name [CTRL-12].
- A controller that cannot reach its host, times out or answers nonsense leaves a
  line in its own log and **never fails your turn** [CTRL-11].
- **edgar learns from what you type and from what breaks (v3, M12).** A line that
  starts with `remember that`, `note that` or `keep in mind` becomes a fact, in
  that session, with no `/remember` — and it is printed when it is saved, because
  nothing enters memory quietly. A tool failure that happens three times in a
  project becomes a fact too, built from a template rather than from the error's
  text. Nothing else can: a fetched page, a piped file, an `@path` attachment, a
  tool's output, a subagent's prompt and the model's own words all travel roads
  that never reach a learner, and that is enforced by what each function accepts
  [MEM-8, MEM-9, MEM-22, ADR-0017, ADR-0063].
- **`edgar stats`** prints what this project's runs add up to: how many, how they
  ended, how often a check passed, what they cost, which tools they used and the
  shapes they took (`read+edit+shell`, and so on) [MEM-18, MEM-19].
- **`.edgar/history.md`**, a readable log of every run — what you asked, what it
  said, what it did, which files, how it ended. Redacted on write, condensed when
  a prompt is long, rotated to `history.1.md` before it can grow without bound,
  and **gitignored by default** (OQ-1). `edgar history show` prints it;
  `--no-history` or `[memory] history = false` turns it off [MEM-12..17].
- **`edgar history distill`** proposes facts from recurring patterns in that file.
  They are always **pending**: `history.md` holds model-written text, so nothing
  derived from it is active until you confirm it with `edgar memory review`
  [MEM-17].
- All of it is removable. `edgar.learning` is v3: nothing in Core, v1 or v2
  imports it, it attaches by name through the event bus, and CI deletes the
  package and runs the suite without it [NFR-12].
- **`edgar doctor` finished, and it no longer reaches the network unasked.** It
  now also reports whether this project is trusted, runs `PRAGMA integrity_check`
  on the project and user databases, says whether each stdio MCP server's command
  is on your `PATH`, and whether each extension's required commands are. A plain
  run opens no socket at all: a remote MCP server is not probed, because the only
  probe worth making is the handshake `edgar mcp test NAME` already performs, and
  asking each provider for its model list now needs `--network` — the skipped line
  says so. Note that `--network` uses your key, since listing models is an
  authenticated call for most providers; it costs no tokens [CFG-5, ADR-0062].
- **`edgar route explain [PROMPT]`** prints which model each role would get, which
  `[[route]]` rule decided and why, then every rule with matched or skipped against
  a main turn. It calls the same pure function a turn calls, contacts no provider
  and needs no key [ROUTE-9].
- **`edgar agents list|validate`** lists every agent a session here would find,
  with its scope and model, and reports every file it had to skip with the line
  the mistake is on.
- **`edgar ext validate PATH` and `edgar ext add PATH`.** `validate` loads a
  bundle with the same loaders a session uses and prints what would break. `add`
  refuses to copy anything unless that passes, then audits every skill it would
  copy and shows you the report before writing. The question defaults to yes when
  the audit is clean and to no when there is a danger finding; with no terminal a
  danger finding is refused unless you pass `--yes`. The copy is staged and moved
  into place in one step, so a half-installed extension is not a state you can end
  up in [EXT-3].
- **`edgar skills audit PATH [--strict] [--diff]`** runs that audit on its own.
  Conformance findings set the exit code; danger findings are listed apart —
  piped downloads, `sudo`, recursive deletes, `eval`, instructions to widen policy
  or skip checks, "don't tell the user", hidden and bidi characters, HTML
  comments, long base64 runs, credential locations, every host named, and every
  bundled script with the programs it calls. `--diff` prints the fixes it would
  make and never applies them; the audit writes nothing. No model is asked for an
  opinion, because the text under review may be written to talk one out of its
  verdict. A clean audit means no known pattern matched — not that the skill is
  safe [SKL-18, ADR-0042].
- **A subagent that writes can get its own git worktree.** An agent whose
  frontmatter says `isolation: worktree` runs in `.edgar/worktrees/<agent>-<session>`
  on a branch called `edgar/<agent>-<session>`, so two agents editing the same
  file finish on two branches and your working copy is never touched. The tree is
  cut from your last commit, so an edit you have not committed yet is invisible to
  it and safe from it. When the agent is done: if the tree is clean it is removed
  and the branch keeps the commits; if anything at all is uncommitted, **the tree
  is kept** and its path, branch and diff stat are printed in the agent's summary,
  along with the `git worktree remove` line to delete it yourself. Nothing is ever
  forced and nothing you did not write is ever thrown away. Outside a git
  repository the agent is refused rather than quietly run unisolated [SUB-11,
  ADR-0061].
- **`[shell] sandbox` runs commands inside the platform's own walls.** `bwrap` on
  Linux, `seatbelt` on macOS, `none` (the default) everywhere. It applies to
  `shell`, to command tools you declared and to the verify command. The confined
  process may write only where edgar was launched and where spilled output goes,
  and reaches the network only when the permission engine already said it could —
  so a session that has read untrusted content loses the network in the sandbox
  too. **It confines writes and the network, not reads:** a confined command can
  still read your files, which is what the design specifies and is said plainly
  rather than overclaimed. A backend you configure but do not have ends the
  session with an error instead of silently running unconfined, and
  `edgar doctor` now prints a line saying which backend is set and which is the
  best one this machine could run [PERM-15, ADR-0061].
- **Show the model a picture.** `@photo.png` attaches an image the same way
  `@notes.md` attaches text, and the `read` tool on an image file answers with
  the image instead of "looks binary; not shown". PNG, JPEG, GIF and WebP are
  recognised from their first bytes, with no new dependency. The bytes go to
  `sessions/<id>/blobs/` and never into the session's JSONL, so a transcript
  stays readable and small; `--events` carries the reference so a watcher can
  find the file on disk. A model that cannot see refuses an attached image
  **where the model is chosen**, before anything is sent or spent, and says so;
  if a tool produces a picture mid-turn instead, that model is told what the
  file is rather than sent nothing. Images are priced by their dimensions per
  provider, so the context budget and the cost caps stay right, and an old
  picture is elided to a line naming it, so you stop paying for it every request
  [ADR-0052, ADR-0060].
- **Web search, as a file you copy in.** `examples/tools/web_search.toml` is an
  HTTP tool in three documented variants — Brave, Tavily, or your own SearXNG —
  with the key read from the environment at call time and scrubbed from what
  comes back. There is deliberately no default host: you pick one, and you can
  see which one. `examples/skills/web-research/` is the half that matters —
  search, fetch the best hits, answer with the URLs. No code was added for this.
- **git, as four files you copy in.** `git-status`, `git-diff`, `git-log` and
  `git-commit` as command tools: argv templates started directly, never through
  a shell, so a commit message with newlines, semicolons or backticks in it is
  message text. `examples/skills/git/` carries the etiquette, including reading
  the repository's own `AGENTS.md` first, and `examples/extensions/git-trail/`
  is an observe-only `post_tool` hook that logs each commit. No code was added
  for this either.
- **Attach a file to what you type.** A bare `@path` anywhere in a REPL line or
  in `edgar -p` attaches that file's text to the message as context, leaving the
  line you typed exactly as you typed it. A missing path, a directory, a
  credential file, a path outside the working directory or anything that is not
  text is refused in one sentence naming the path, and the turn does not run —
  never a traceback. A file bigger than `tools.max_output_tokens` spills to
  `sessions/<id>/blobs/` like oversized tool output. Attached text is context,
  not something a human typed, so it can never become a memory fact [CLI-3,
  MEM-9].
- **Plan mode and a `todo` list.** `/plan what should we do about X` (or
  `edgar --plan`) puts the session in `read-only` and asks for a plan: the model
  can read, search and think, and a `write` or `edit` is denied by the ordinary
  permission rules. The plan is pinned just above the current turn, so it
  survives compaction, and is saved to `sessions/<id>/plan.md`. `/go` gives back
  the mode the session had before — never a wider one — and leaves the plan
  pinned. A new `todo` tool lets the model keep a checklist next to the plan;
  the status bar shows `todo 2/5`, and `--resume` brings both back [CLI-20,
  TOOL-14, CTX-18, ADR-0025].
- **`edgar context show [SESSION]`** prints the prompt edgar would send: one row
  per section with its token count, the cache breakpoint marked, the transcript
  below it and the total at the bottom. No provider is called [CTX-2].
- **`edgar sessions compact ID`** runs the same compaction stages `/compact`
  runs, but on a stored session you are not in. Nothing is rewritten: the stages
  are appended to the session's record, so `--resume` shows the compacted view
  and the original lines are all still there [CTX-10].
- **`edgar config show --resolved`** lists every effective setting with the layer
  it came from — `default`, a config file's path, `env EDGAR_…` or a flag — so
  "which file won" is one command. API keys render as `***`; edgar stores the
  name of an environment variable, never a key [CFG-2, CFG-6].

### Fixed
- A `[[route]]` rule keyed on `mode`, such as one routing `read-only` turns to a
  cheaper model, could never match your main turn: the routing context it was
  checked against left every field but the role at its default. `mode` and
  `tools_required` are now the real ones for that turn; `tags` and `schedule`
  stay unset, since nothing in edgar produces either yet [ROUTE-2].

### Docs
- The tour covers all of v1 and now has a map. Four new pages —
  [memory](docs/tour/memory.html), [MCP and signing in](docs/tour/mcp.html),
  [subagents](docs/tour/agents.html) and [extensions](docs/tour/extensions.html)
  — walk each v1 feature the way the Core tour walks the loop, and six new Core
  stops cover the seventeen source files that had none. [The
  map](docs/tour/map.html) draws every tier, package and file at a size
  proportional to its lines of code; hover for what a file does, click to open
  its stop. `just map` regenerates it, and a test fails if the committed copy has
  drifted. Every page's header links every other page, and a source file with no
  stop anywhere now fails the test suite (M18,
  [ADR-0058](docs/adr/0058-m18-the-tour-pages-and-the-map-as-built.md)). No
  change to `src/`.
- Every tour stop rewritten for clarity: dense paragraphs are now bullet lists
  where they were really a list of facts or rules, small pseudocode boxes and
  per-stop diagrams replace one big diagram per page, and vocabulary is
  simpler throughout. No change to `src/`.
- Removed the "Start the clock" self-timer widget from `index.html` and the
  `.check` "Before you go" comprehension-question boxes at the end of every
  tour page, with their now-dead CSS and JS. No change to `src/`.

## 1.0.0 — 2026-09-16

v1 whole: memory and session search, MCP and signing in (already in 0.1.0),
subagents, routing and fallback, extensions, hooks, provider plugins, `edgar
init` and `doctor`, and the docs that teach all of it. Extension formats are
frozen. 8,000 of 8,000 lines of code.

### Added
- Subagents. A `task` tool appears once any agent is discovered in
  `.edgar/agents/` or `~/.edgar/agents/`: pick one by name and it runs in a fresh
  session, with its own model (routed for role `subagent`, or its own
  frontmatter `model:`), its own tool subset, and a `mode:` that can only ever
  narrow the calling session's, never widen it. It shares the parent's
  permission guard, so its prompts ask one at a time alongside the main turn's
  own and are labelled with the agent's name; its budget is capped at whatever
  the parent has left to give, and a result that ran out of budget says so
  rather than passing a truncated answer off as whole. An agent already running
  above itself, or a call past `[subagents] max_depth`, is refused rather than
  run. Ask the model for several subagents in the same turn and they run
  together, bounded by `[subagents] max_parallel`; everything else still runs
  one call at a time, and results come back in the order they were asked for,
  not the order they finish.
- Each subagent running now gets its own row under the main status line, so
  two or more running together never interleave into one confusing stream; a
  row appears when its `task` call starts and disappears once it finishes.
- An example agent, `examples/agents/code-reviewer.md`: copy it into
  `.edgar/agents/` and the `task` tool can hand it a diff or a file to review
  read-only, with no `write`, `edit` or shell access.
- A model with no tool support is now refused where it is chosen — a subagent
  asking for one gets a plain tool error back; the main session choosing one
  with `/model` or at startup gets a config error — instead of failing
  confusingly the first time a turn tries to call a tool.
- Extensions: a folder under `.edgar/extensions/` bundling tools, skills,
  agents and one `hooks.toml`, found the same way skills and agents already
  are. `edgar ext list` shows what is discovered. A hook can observe or veto,
  never allow — every kind fires as an event, and `pre_tool` alone runs just
  before the permission check; a hook that errors, times out or exits
  non-zero denies the call rather than letting it through.
- Provider plugins: a third-party package can register a provider through the
  `edgar.providers` entry point; nothing is imported unless a session actually
  names it.
- Skills can now activate on their own: a keyword the user typed or a path the
  last round touched loads a matching skill straight into the turn, with no
  need for the model to call the `skill` tool first. A skill's own `verify:`
  command now also takes its place in the verify precedence chain, below
  `--verify` and an agent's own frontmatter.
- `edgar.run()`: an async Python function to embed edgar in another program —
  build a session and run one turn the same way the CLI does, with your own
  event subscribers and your own function to answer permission prompts.
  `import edgar` stays as light as `import edgar.cli.main`.
- Three more slash commands: `/agents` lists the subagents this session's
  `task` tool can run, `/skills` lists the skills it can load, `/tools` lists
  every tool available.
- `edgar init` and `/init`: scaffolds a project's `AGENTS.md`, a `.gitignore`
  fragment for `.edgar/`'s generated state, and a commented `config.toml`
  with a model already picked when there is a terminal to ask. Never
  overwrites a file that is already there. Starting `edgar` in a project
  with nothing configured now offers to run this instead of erroring.
- `edgar doctor`: checks each provider's credentials and connectivity, and
  warns when the project or home directory sits in an iCloud Drive, OneDrive,
  Dropbox or Google Drive folder, where SQLite wants extra care.
- Two more ways to get edgar onto a machine, alongside `uv tool install` and
  `uvx`: every GitHub release now attaches a self-installing binary per
  platform (Linux, macOS, Windows), and `ghcr.io/vespassassina/edgar` carries
  a prebuilt Docker image, both built from the same PyPI release.
- `docs/EXTENDING.md` (add a provider, a tool, a subagent, a skill, an
  extension) and `docs/DEPENDENCIES.md` (every dependency, with its measured
  import cost) join the Cookbook as the project's onboarding docs.
- An example extension, `examples/extensions/audit-log/`: copy it into
  `.edgar/extensions/` for a manifest plus one hook that appends a line to a
  local log at the end of every turn.
- An example HTTP tool that needs no API key, `examples/tools/weather.toml`:
  copy it into `.edgar/tools/` for current weather by city from wttr.in.
- Five example command tools for OAuth-authenticated services, wrapping a
  maintained third-party CLI instead of a hand-written client:
  `examples/tools/dropbox_ls.toml` and `onedrive_ls.toml` wrap `rclone`;
  `gmail_search.toml`, `gcal_events.toml` and `gdocs_get.toml` wrap
  [`gws`](https://github.com/googleworkspace/cli). Sign-in happens once,
  outside edgar, with `rclone config` and `gws auth setup`.

### Changed
- The roadmap after 1.0 is re-tiered ([ADR-0057](docs/adr/0057-daily-driver-before-learning.md)):
  2.0 is now the daily driver (tour pages, `@path`, plan mode and `todo`, images,
  web search and git as extensions, worktrees and sandboxes, the inspection
  commands); learning and the controller move to 3.0, the broker and scheduling
  to 4.0. Nothing in the running code changes; `/plan` still says it arrives in v2,
  which is now true again.
- A `[[route]]` rule with a key edgar does not recognise is now a config error
  naming the rule. A misspelt condition used to be dropped, so the rule matched
  every turn.
- `/plan` says it arrives in v2; plan mode moved there before 1.0.
- `edgar models` offers to sign in instead of sending you away. Picking a provider
  that has no key but can issue one through the browser now asks "no key for
  openrouter. Sign in now? [Y/n]" — Enter signs in and the picker carries straight
  on to that provider's models, using the key it just got even if there is no
  keyring to keep it in. Answer `n` and you get the old message naming the
  environment variable. A provider with no browser sign-in (OpenAI, Anthropic) is
  unchanged: its key is named, never asked for.

### Fixed
- Two sessions started within the same millisecond (a fork right after its parent,
  a script starting several) could sort in the wrong order, so `edgar --continue`
  could reopen the older one. An id now never reuses the previous one's
  millisecond.
- The tour said M7 to M17 were planned; M7 (memory) and M8 (MCP, signing in) have
  been built since 0.1.0. It now says M0 to M8 built, M9 to M17 planned.

### Security
- `fetch` and any HTTP tool could be sent to the cloud instance-metadata address
  (169.254.169.254 and the rest of that range) in `auto` mode before the session
  was even tainted, and in `yolo` always. A URL that literally names a link-local
  address is now denied in every mode, the same hard layer as catastrophic shell
  commands. A hostname that merely resolves there still gets through; see
  [ADR-0049](docs/adr/0049-network-hard-layer.md) for what this does and does not
  cover.

## 0.1.0 — 2026-09-14

The first release that is a harness rather than a skeleton: Core (M0–M6) whole,
plus memory, session forks, MCP and signing in from v1 (M7, M8). 6,809 lines of
code of the 8,000 v1 is allowed.

### Added
- [A Tour of the Harness](https://vespassassina.github.io/edgar/): a guided read
  of the code, stop by stop, with diagrams, one part per tier, styled with
  artifactkit on a dark midnight theme.
- `edgar -p PROMPT` runs one turn (M1): the turn loop, the `read` and `ls` tools,
  deny-by-default permissions (reads inside the working directory only), the
  system prompt as a file (`edgar prompt show`), and layered config with
  provenance and error messages that name the file, the key and the expected type.
- Real providers (M2): `openai/…`, `azure/…`, `openrouter/…`, `ollama/…`,
  `anthropic/…`, and any OpenAI-compatible server as a `[providers.NAME]` block.
  Keys come from the environment only; a missing key fails before any request.
- Retries with backoff on 429 and 5xx, honouring `Retry-After`.
- Deterministic repair of malformed tool calls from small models (code fences,
  trailing text, JSON written as text); `native_tools = false` for servers with no
  tool support.
- Cost per request: a small dated price table, `[pricing."provider/model"]`
  overrides, provider-reported cost for OpenRouter, zero for Ollama, and "unknown"
  instead of a wrong zero for everything else.
- `edgar models list`: where each role's prompts go and whether each provider's
  key is set, without contacting anything.
- A compact system prompt for models with under 32k tokens of context.
- The interactive REPL (M4): `edgar` on a terminal. Keep typing while it works:
  plain text queues the next prompt, `/steer` corrects the turn in flight, `/btw`
  asks a side question without touching the conversation. `/stop` or Ctrl-C
  cancels (twice exits), `/pause` and `/resume`, `/status`, `/cost`, `/mode`,
  `/thinking`, `/title`, `/new`, `/clear`, `/help`. A status line under the prompt.
- `edgar models` and `/model`: pick a provider and one of its models; the default
  goes into a new config file, never into an existing one.
- Writing and running (M3): `write`, `edit`, `glob`, `grep`, `shell` (Git Bash,
  PowerShell or your POSIX shell) and `fetch`.
- Permissions: four modes, `[permissions]` rules per tool, `write_paths`,
  `shell_allow` and `shell_deny`; in the REPL, answer once, for the session, or
  always (stored as a grant; `edgar permissions list|revoke`). Anything outside
  the working directory asks; credentials are off limits; writing edgar's own
  config and instruction files always asks. After reading web content, `auto`
  asks before the shell or the network. `-p` exits 5 when a call needed a prompt.
  yolo needs `EDGAR_YOLO=1` or the word typed.
- The verify gate: `--verify CMD` or `[verify] command` runs your check when the
  model stops after changing something; failures go back to the model, and `-p`
  exits 9 when the attempts run out.
- Command tools and HTTP tools in `.edgar/tools/*.toml` and `~/.edgar/tools/`: a
  CLI or an API for the agent, with arguments as whole argv elements, a fixed host
  and secrets from the environment, scrubbed from output.
- Project trust: a project's own tools and verify command run only after
  `edgar trust`; `--no-project-exec` runs without them.
- `-p` for programs: `--json` (one object), `--events` (JSON Lines), `--quiet`,
  `--show-thinking`, `--no-color` and `NO_COLOR`; piped stdin is attached as
  context; a status line on stderr when it is a terminal; Ctrl-C exits 7.
- Sessions (M5): every session is recorded to `.edgar/sessions/<id>.jsonl`
  (git-ignored, one JSON object per line). `edgar --resume [ID]` and `--continue`
  reopen one, compacted view and all; `edgar sessions list|show ID|rm ID`; in the
  REPL `/sessions`, `/load ID`, `/new`, `/reset`, `/undo [N]` (files stay as they
  are, and it says which) and `/retry`.
- Long sessions compact themselves (M5): old tool results become one-line stubs,
  then old turns fold into one summary, cheapest first; `/compact [FOCUS]` does it
  now. Content that cannot fit the window stops with a hint instead of being cut.
- Cost caps: `[budget] turn_cost_cap` and `session_cost_cap` stop the turn before
  the next request; `-p` exits 6 with the partial result. With a cap set, a model
  of unknown price stops at once.
- `personality.md` (project `.edgar/` or `~/.edgar/`) for tone and style, shown by
  `edgar prompt show`; `~/.edgar/AGENTS.md` for instructions in every project.
- A warning at start when edgar's own control files (AGENTS.md, config, tools)
  changed during the previous session.
- Skills (M6): a folder with a `SKILL.md`, in the format Claude uses, in
  `.edgar/skills/` or `~/.edgar/skills/`. The prompt lists each skill's name and
  description; the model loads the rest with the `skill` tool when it fits. A
  project's skill replaces a user one of the same name, with a warning at start.
  A broken `SKILL.md` is skipped with its reason, never fatal.
- `edgar skills list|validate` (validate exits 1 when a skill has a problem) and
  `edgar tools list|describe NAME`, which shows the tools a session here gets.
- `examples/`: a command tool, an HTTP tool and a skill to copy, and
  [`docs/COOKBOOK.md`](docs/COOKBOOK.md), short recipes for the first week.
- A quick start in the README.
- Sign in without a key: `api_key_command` in a `[providers.NAME]` block of
  `~/.edgar/config.toml` runs your cloud's CLI (`az account get-access-token`,
  `gcloud auth print-access-token`, or AWS's Bedrock token generator) and sends
  its token, refreshed every ten minutes. Works for Azure with keys switched off,
  Google Vertex AI and Amazon Bedrock; recipes in the Cookbook.
- Memory (v1, M7): `/remember TEXT` or `edgar memory add TEXT` saves a fact, and
  from the next session it is in the prompt as a note, not an instruction.
  `edgar memory list|edit|review|forget ID|undo` shows and changes what edgar
  remembers; `edit` opens the facts as markdown in your editor, and `undo` takes
  back the last change whole. When the model proposes a fact with `remember`,
  edgar asks `save? [y/N]` at the end of the turn; Enter forgets it. Secrets are
  redacted before anything is stored.
- `recall`: the model searches remembered facts and past sessions' conversation
  (never tool output), by word and by fragment of a path or identifier. `[memory]`
  in config sets how many facts are pinned (20) and the cap per scope (500).
- Session forks (M7): `/fork` or `edgar --fork ID[@TURN]` branches a session into
  a new one, from its latest turn or from turn N; the original is untouched.
- `/save [PATH]` writes the session to one file with spilled tool output included
  and secrets redacted; `/load PATH` or `edgar --load PATH` opens it as a new
  session. `/history` shows the whole conversation, compacted turns included.
- `[budget] daily_cost_cap`: the day's spend across every project; a turn gets
  what is left of it as its cap, and once it is spent turns stop with exit 6.
  `edgar cost` shows today and the last seven days; `/cost` adds today's total.
- MCP servers (v1, M8): `[mcp.NAME]` blocks in config, over stdio (`command`) or
  Streamable HTTP (`url`). Nothing starts when a session starts: edgar remembers
  what each server offered last time and starts the server on the first call, so
  five configured servers cost a session nothing. Their tools are named
  `mcp__server__tool`, their results are untrusted (they tighten what the rest of
  the session may do), and what a server claims about its own tools is shown to
  you, never used to decide. `${env:NAME}` in `env`, `url` and `headers` is read
  when the server starts and redacted from everything it sends back.
- `tool_search`: when the tool schemas would cost more than `[tools]
  schema_budget` (4,000 tokens), the MCP ones are listed by name and one line and
  their full schemas are loaded on demand, for the rest of the session.
- `edgar mcp list` shows every configured server and its tools, with the hints the
  server publishes; `edgar mcp test NAME` starts one server and reports what it
  answered. A project's `[mcp.NAME]` needs `edgar trust` first.
- `/browser`: with `[browser] tool = "..."` it checks the tool you already have,
  with `[browser] command = ...` it starts that MCP server for this session, and
  with neither it prints the block you could write. It never picks a browser.
- Signing in (M8): `edgar login openrouter` opens your browser, and the key the
  provider issues is yours, kept in your OS keyring with the optional extra
  (`pip install 'edgar-harness[keyring]'`) or printed once and stored nowhere.
  `edgar logout PROVIDER` forgets it here; revoke it where it was issued.
  `edgar models list` says which providers are signed in.
- `edgar mcp login NAME` signs in to a remote MCP server: OAuth 2.1 with PKCE, a
  redirect caught on a loopback port, the client registered on the spot, and a
  token scoped to that server. A turn never opens a browser by itself; a call to a
  server with no token fails with the command to run. `edgar mcp logout NAME`
  forgets it. Tokens are redacted from everything edgar prints or records.

### Changed
- `edgar sessions rm` refuses a session that has forks, since they read its file.
- `edgar models`: pressing Enter at "make it the default?" now saves it to your
  user config; it used to mean no.

## 0.0.2 — 2026-09-13

### Added
- An `edgar-harness` command, so `uvx edgar-harness` works.

## 0.0.1 — 2026-09-13

### Added
- The package skeleton (M0): `edgar --version` on Linux, macOS and Windows,
  Python 3.12 and 3.13.
