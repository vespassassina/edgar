---
name: edgar
description: How edgar itself works. Load it when asked about edgar's commands, config, permission modes, tools, skills, agents, hooks, extensions, memory, sessions or limits, or how to change any of them.
when:
  keywords: [edgar]
---

# What edgar is

A terminal agent harness. Any model, no hidden calls, nothing is done until it is
verified. You are running inside it. Everything below is what edgar does today;
if a thing is not listed, say you do not know rather than guess.

## Where things live

- User scope `~/.edgar/`, project scope `./.edgar/`. The project wins.
- `config.toml` in either. Layers: defaults, user, project, `EDGAR_*` env, flags.
  Read once at session start: a change applies the next time edgar starts.
- `AGENTS.md` in the project: instructions read into every session.
- `.edgar/tools/*.toml` tools, `.edgar/skills/NAME/SKILL.md` skills,
  `.edgar/agents/NAME.md` subagents, `.edgar/extensions/NAME/` bundles.
- `sessions/` hold the JSONL record of every session; `history.md` is its log.
- Never edit `AGENTS.md` or `config.toml` unless the user asked for exactly that.

## Permission modes (`--mode`, `/mode`)

`read-only` reads only. `ask` asks before each write or command. `auto` allows
writes inside the project and asks about the rest. `yolo` checks nothing and
needs a typed confirmation. Content from the network taints a session, and a
tainted `auto` session asks before shell and network calls. Humans widen
permissions; you never do.

## Slash commands in the REPL

`/help` lists them all. The ones people ask about:
`/model` pick or switch a model, `/mode`, `/plan` and `/go` (plan read-only,
then act), `/steer` correct a running turn, `/queue`, `/btw` side question,
`/stop` or Esc or Ctrl-C cancel the turn, `/pause` `/resume`, `/compact`,
`/undo` `/retry`, `/sessions` `/load` `/fork` `/save`, `/cost`, `/status`,
`/remember`, `/memory`, `/skills` `/agents` `/tools`, `/init`, `/quit`.

## Other commands

`edgar init` (config, AGENTS.md, model, a few settings), `edgar doctor`,
`edgar models [list]`, `edgar login PROVIDER`, `edgar trust`,
`edgar tools list|describe NAME`, `edgar skills list|validate`,
`edgar memory list|add|review|forget`, `edgar sessions list|show|rm`,
`edgar mcp list|test|login`, `edgar cost`, `edgar prompt show`,
`edgar permissions list|revoke`, `edgar schedule list|add|remove|run`.
`edgar -p "task" --mode auto` runs one turn without a terminal.

## Tools

Built in: `read`, `ls`, `glob`, `grep`, `write`, `edit`, `shell`, `fetch`,
`todo`, plus `task` (subagents), `skill`, memory and tool search where they are
available. Consecutive read-only calls run at the same time; everything else
runs in order. More tools are files: a command tool (an argv template, never a
shell), an HTTP tool (a fixed host), or an MCP server (`[mcp.NAME]` in config).
Project tools need `edgar trust` once. Web search and git are tools of this
kind: `edgar init` offers them, or copy `examples/tools/*.toml`.

## Models and providers

`provider/model`, for example `anthropic/claude-opus-4-5`. `edgar models` picks
one and can save it as the default. Providers: OpenAI, Anthropic, Azure,
OpenRouter, Ollama, GitHub Copilot, and any OpenAI-compatible server in a
`[providers.NAME]` block. A key lives in an environment variable or the OS
keyring, never in a file.

## Memory, skills, verification

- Facts: `/remember TEXT` or `edgar memory add`. A fact the model proposes is
  pending until a human confirms it.
- Skills: a folder with `SKILL.md`. You load one by calling the `skill` tool.
- Verification: `[verify] command` in config, or `--verify CMD`. When you stop
  after changing files it runs; if it fails, the output comes back to you.

## What edgar does not do

No GUI, no server mode, no vector index, no skill marketplace, no messaging
gateway, no language-server tools, no notebook editing, no background
processes. Say so when asked for one.

## More

Full docs: https://github.com/vespassassina/edgar/tree/main/docs
(`COOKBOOK.md` for recipes, `EXTENDING.md` for tool, skill, agent and extension
formats, `PRD.md` for the requirements). Fetch a page when the user needs depth.
