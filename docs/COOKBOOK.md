# Cookbook

Short recipes for things people do with edgar in their first week. Each one works
as written in Core (0.x). The files they copy are in [`examples/`](../examples/),
and a test loads every one of them, so a recipe cannot quietly go stale.

## Start a new project

```bash
cd your-project
edgar init          # or /init from inside the REPL
edgar doctor
```

`edgar init` scaffolds `.edgar/config.toml`, an `AGENTS.md` stub and a
`.gitignore` fragment, all sensibly commented, and never overwrites a file
that is already there [CFG-4]. `edgar doctor` checks credentials and
connectivity for every provider your config names, and warns when the
project (or your home directory) sits inside a cloud-synced folder — iCloud
Drive, OneDrive, Dropbox, Google Drive — since SQLite there wants care
[CFG-5].

## See what a session has done, and undo it

```bash
edgar permissions list
edgar permissions revoke 12
```

A grant recorded once (an "always allow" answer to a permission prompt)
lives in `.edgar/edgar.db`, not in a config file, so no automated component
can ever widen it [PERM-6, ADR-0021]. `revoke ID` deletes one grant by the
id `list` printed; the next matching call asks again.

## Sign in without an API key

```bash
edgar login anthropic     # opens a browser, OAuth 2.1 with PKCE on a loopback port
edgar logout anthropic    # forgets it
```

The token lives in the OS keyring, never in a config file [CFG-6, PRV-18]; a
turn itself never opens a browser, only this command does. Only providers
that issue keys this way accept `login` — for everything else, an
environment variable or `api_key_command` (see "Sign in with your cloud
identity" below) is how a key or token reaches edgar.

## Run on a local model, for free

```bash
ollama pull qwen3:8b
edgar --model ollama/qwen3:8b
```

Nothing leaves your machine. Small models that write their tool calls as fenced
or plain JSON are repaired deterministically. To make it the default, run
`edgar models`, choose `ollama` and the model, and press Enter to save it.

## Sign in with your cloud identity, no keys

Azure, Google Cloud and AWS can hand out short-lived tokens instead of keys, and
Azure is switching keys off. Sign in with the cloud's own CLI, then name the
command that prints a token in `~/.edgar/config.toml`:

```toml
# ~/.edgar/config.toml  (your user config: a project's config may not name a command)

[providers.azure]                      # Azure OpenAI with Entra ID: az login
base_url = "https://YOUR-RESOURCE.openai.azure.com"
api_key_command = ["az", "account", "get-access-token", "--resource",
                   "https://cognitiveservices.azure.com", "--query", "accessToken", "-o", "tsv"]

[providers.vertex]                     # Google Vertex AI: gcloud auth login
kind = "openai-compatible"
base_url = "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/YOUR-PROJECT/locations/us-central1/endpoints/openapi"
api_key_command = ["gcloud", "auth", "print-access-token"]

[providers.bedrock]                    # Amazon Bedrock: aws sso login, and AWS_REGION set
kind = "openai-compatible"
base_url = "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1"
api_key_command = ["uv", "run", "--no-project", "--with", "aws-bedrock-token-generator", "python", "-c",
                   "from aws_bedrock_token_generator import provide_token; print(provide_token())"]
```

```bash
edgar --model azure/YOUR-DEPLOYMENT
edgar --model vertex/google/gemini-2.5-flash
edgar --model bedrock/openai.gpt-oss-120b
```

edgar runs the command directly, never through a shell, and sends what it prints
as a bearer token. It runs again once the token is ten minutes old, so a long
session outlives the cloud's one-hour tokens. A key in the environment still
wins: Azure uses `AZURE_OPENAI_API_KEY` if it is set. If your sign-in has lapsed,
edgar stops before sending anything and shows the cloud's own error. Azure's role
for this is "Cognitive Services OpenAI User".

## Use it in a pipe

```bash
git diff | edgar -p "review this for bugs, output markdown" --mode read-only
edgar -p "summarise" --json < notes.txt | jq -r .result
```

Piped input is context for the prompt, never the prompt itself. stdout carries
only the answer, and status goes to stderr, so `> out.txt` holds just the
result. `-p` needs `--mode`: nobody is there to answer a question, so you choose
up front what it may do.

## Attach a file to what you type

```bash
edgar -p "explain @README.md in one paragraph" --mode read-only
```

In the REPL and in `-p`, a word starting with `@` attaches that file's text to
your message. Like piped input it is context, never the prompt, and like piped
input it is never a learning source: nothing you attach can turn into a
remembered fact. Text files only, inside the working directory; a directory, a
binary file or a path that is not there gets a message naming it, and the turn
does not run. A file bigger than `tools.max_output_tokens` keeps its head and
tail and spills the rest to a blob, exactly as large tool output does.

## See exactly what edgar is about to send

```bash
edgar context show          # the latest session in this project
edgar context show a1b2c3   # or one by id
```

One row per section of the assembled prompt, in order, with its token count and
the cache breakpoint drawn where it falls: the system prompt, your personality
and instruction files, pinned facts, the skill index, then the transcript, the
working state and the current turn. It calls no provider and costs nothing; it
runs the same assembly a turn runs, so what it prints is what would be sent.

## Shrink a session you are not in

```bash
edgar sessions compact a1b2c3
```

Runs the same stages `/compact` runs, against a stored session: old tool results
become stubs, old turns fold into one summary. It appends the stages to that
session's record rather than rewriting it, so nothing is lost and `--resume`
replays to the compacted view. Folding costs one model call, and it says what
it did.

## Find out which config file won

```bash
edgar config show --resolved
```

Every effective key, its value, and the layer it resolved from: `default`, the
path of the user or project config that set it, or the environment variable that
overrode both. Nothing in a config file is ever a key — only the name of the
variable holding one — so a provider's key shows as `***` with the variable it
came from, never the key itself.

## Give the agent a CLI

A command tool is an argv template. edgar starts the program directly, never
through a shell, so an argument like `; rm -rf ~` is one odd argument, not a
second command.

```bash
mkdir -p .edgar/tools
cp examples/tools/gh_issue.toml .edgar/tools/
edgar trust          # a project's tools run only once you trust it
edgar tools describe gh_issue
```

`read_only = true` in the file is your statement that the command changes
nothing, so it is allowed without asking, like `read`. Leave it out for anything
that writes.

An OAuth-authenticated service is still a command tool, not MCP, if a
maintained CLI for it already exists: wrap that CLI's own argv rather than
writing a client. `edgar` never runs the sign-in step —
[`examples/tools/dropbox_ls.toml`](../examples/tools/dropbox_ls.toml) and
[`onedrive_ls.toml`](../examples/tools/onedrive_ls.toml) wrap `rclone`, whose
`rclone config` does Dropbox's and OneDrive's OAuth once, outside edgar;
[`gmail_search.toml`](../examples/tools/gmail_search.toml),
[`gcal_events.toml`](../examples/tools/gcal_events.toml) and
[`gdocs_get.toml`](../examples/tools/gdocs_get.toml) wrap
[`gws`](https://github.com/googleworkspace/cli) the same way, one `gws auth
setup` covering all three Workspace APIs. Each file is still just an argv
template with `{slot}`s — the underlying CLI's own command line is the
contract, so there is nothing to maintain when that CLI adds a feature.

## Give the agent an API

An HTTP tool is a request template with its host fixed. Arguments fill only the
path, query and body. `${env:NAME}` fills headers from the environment, and the
value is scrubbed from everything the tool returns, so the token never reaches the
transcript.

```bash
cp examples/tools/service_status.toml .edgar/tools/
export STATUS_API_TOKEN=...
edgar trust
```

Edit `url` to point at your API first. The response is marked untrusted: in
`auto` mode, shell and network calls after it ask before they run.

Not every API needs a token: [`examples/tools/weather.toml`](../examples/tools/weather.toml)
calls wttr.in, which takes no auth, so the file has no `headers` and nothing
to fill from `${env:NAME}` — `${env:NAME}` is only for the APIs that need it.

```bash
cp examples/tools/weather.toml .edgar/tools/
edgar trust
```

## Working with git

edgar has no built-in git support, on purpose: git is a CLI, and a CLI is four
small argv templates you can read.

```bash
cp examples/tools/git-status.toml examples/tools/git-diff.toml \
   examples/tools/git-log.toml examples/tools/git-commit.toml .edgar/tools/
cp -r examples/skills/git .edgar/skills/
edgar trust
edgar tools list
```

The three that only look are `read_only = true`, so they run without asking.
`git-commit` is not: it writes, so it goes through the guard like any other
write. Its message is **one argv element**, which is the whole reason this is a
command tool and not a shell string — newlines, backticks and semicolons in a
commit message stay message text, because no shell ever sees them.

There is deliberately no `git-add`, and no push, merge or tag. Staging is where
a human decides what goes in, and the rest are the user's calls; the `git` skill
says so, along with reading the repository's own `AGENTS.md` first and matching
the house style in `git-log`.

To keep a note of what the agent committed, add the
[`git-trail`](../examples/extensions/git-trail/) extension: a `post_tool` hook
matched to `git-commit` that appends one line per commit to a local log.

```bash
mkdir -p .edgar/extensions
cp -r examples/extensions/git-trail .edgar/extensions/
edgar trust && edgar ext list
```

`post_tool` is observation only — fired and forgotten, its output never reaching
the model [EXT-6]. It learns *that* a commit happened, not what the tool
printed, so the script reads the commit back out of git itself. Only `pre_tool`
can stop a call.

## Search the web

edgar ships no search engine and no default search host: web search is an HTTP
tool you copy in, so the host is in a file you can read [PRV-15].
[`examples/tools/web_search.toml`](../examples/tools/web_search.toml) has three
variants — Brave, Tavily, and your own SearXNG instance. Brave is the active one;
uncomment the one you want and delete the rest.

```bash
cp examples/tools/web_search.toml .edgar/tools/
export BRAVE_SEARCH_API_KEY=...
edgar trust
edgar tools list             # web_search  http  project  Search the web…
edgar tools describe web_search   # its schema, category and read_only
```

The key is read at call time, not when the file loads, so `edgar tools list`
works before you set it; whatever it resolves is scrubbed from the tool's
output. Searching alone rarely answers anything, so pair it with the built-in
`fetch` and the `web-research` skill, which tells the model to search, fetch the
best two or three hits, and answer with the URLs it used:

```bash
cp -r examples/skills/web-research .edgar/skills/
edgar skills validate
```

```
$ edgar -p "what changed in the latest uv release?"
```

A search result and a fetched page are untrusted output: in `auto` mode, shell
and network calls after one arrive ask before they run [PERM-11]. Read what the
model quotes, not just its conclusion.

## Write a skill

A skill is know-how the agent loads when it needs it: a folder with a `SKILL.md`,
in the same format Claude uses.

```bash
mkdir -p .edgar/skills
cp -r examples/skills/changelog .edgar/skills/
edgar skills validate
```

```markdown
---
name: changelog
description: Use when adding an entry to CHANGELOG.md, or when asked what changed for users since the last release.
---

# Writing a changelog entry
1. Read `CHANGELOG.md` and find the `## Unreleased` section. …
```

Only `name` and `description` go into the prompt. The body loads when the model
calls the `skill` tool, so write the description as *when to use it*: it is all
the model sees before choosing. `name` must match the folder name. Files beside
`SKILL.md` (templates, scripts) are found from the body by relative path. A
script runs through the `shell` tool, under the same permission checks as any
other command.

Put a skill in `~/.edgar/skills/` to have it in every project. A project's skill
replaces a user one with the same name, and edgar says so when it starts.

## Hand work to a subagent

An agent is one flat markdown file: frontmatter naming its tools and mode, then
its system prompt. It runs in a fresh session with a narrowed policy — it can
never ask for anything wider than the mode the calling session is in [PERM-8].

```bash
mkdir -p .edgar/agents
cp examples/agents/code-reviewer.md .edgar/agents/
edgar tools list        # `task` appears once an agent file exists
```

There is no `edgar agents list` (cut from 1.0, [ADR-0053](adr/0053-what-1-0-actually-ships.md)).
Ask the model to use `task` with `code-reviewer` and a description of what to
review; it runs with its own budget and reports back, unable to edit anything
since `code-reviewer.md` grants only `read`, `ls`, `glob` and `grep`.

## Bundle tools, skills and agents into an extension

An extension is a folder behind one manifest, so a team can share a whole
setup — tools, skills, agents, and hooks that observe or veto a turn — as one
`cp -r` or one git submodule, instead of copying files one at a time.

```bash
mkdir -p .edgar/extensions
cp -r examples/extensions/audit-log .edgar/extensions/
edgar trust
edgar ext list
```

```toml
# .edgar/extensions/audit-log/hooks.toml
[[hooks]]
event = "turn_end"                 # observation only: cannot block or change anything
command = ["python", "log_event.py"]
```

Every event but `pre_tool` is fire-and-forget: its exit code and output are
never read, so a broken hook here changes nothing about the session it
watches. A `pre_tool` hook is the one that can say no — exit 2 denies the
call with stderr as the reason shown to the model, and it fails closed on
any other error or a timeout, never open. There is no `edgar ext validate` or
`edgar ext add` in 1.0 ([ADR-0053](adr/0053-what-1-0-actually-ships.md));
`edgar ext list`'s warnings are the check. [`EXTENDING.md`](EXTENDING.md)
has the full manifest and hook grammar.

## Make "done" mean your tests pass

```bash
edgar -p "bump httpx and fix what breaks" --mode auto --verify "just check"
```

When the model stops calling tools after a turn that changed something, edgar
runs the check itself. A failure goes back to the model with the output, up to
`max_attempts` runs (default 2). Exhausted, the run exits 9. To keep the check
for every run in a project, put it in `.edgar/config.toml` (this also needs
`edgar trust`):

```toml
[verify]
command = "just check"
```

## Run untrusted work in a container

The permission engine is a speed bump, not a boundary: it says so in
[BLUEPRINT §7.4](BLUEPRINT.md#74-residual-risks). For a repository you did not
write, or any prompt built from web content, put a real wall around it. A
minimal one:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /work
ENTRYPOINT ["uvx", "edgar-harness"]
```

```bash
docker build -t edgar-sandboxed .
docker run --rm -it -v "$PWD":/work -e OPENAI_API_KEY edgar-sandboxed
```

The container's own network and filesystem limits hold even against a model
talked into something by injected text; the permission engine's mode, taint and
hard-layer checks (PERM-1..16) still run inside it, on top. Neither replaces the
other — [ADR-0021](adr/0021-humans-widen-machines-tighten.md) is the reasoning.

The repo's own [`Dockerfile`](../Dockerfile) is this same shape, published per
release to `ghcr.io/vespassassina/edgar` so `docker pull` replaces the build.

## Pick up where you left off

```bash
edgar --continue          # the latest session here
edgar sessions list
edgar --resume 01J8       # any unique prefix of an id
```

Sessions are JSON Lines under `.edgar/sessions/`, appended to and never
rewritten. Compaction shortens what the model is sent, never what is on disk.

## Put a ceiling on cost

```toml
# .edgar/config.toml
[budget]
turn_cost_cap = 0.50      # dollars
session_cost_cap = 5.00
```

A cap stops the turn with a clear message, and `-p` exits 6. It never switches
models to save money.
