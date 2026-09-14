# Cookbook

Short recipes for things people do with edgar in their first week. Each one works
as written in Core (0.x). The files they copy are in [`examples/`](../examples/),
and a test loads every one of them, so a recipe cannot quietly go stale.

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
