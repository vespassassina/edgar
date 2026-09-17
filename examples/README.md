# Examples

Files to copy into a project, each one working as it is. Nothing here is loaded
until you copy it.

| Example | What it is | Copy it to |
|---|---|---|
| [`tools/gh_issue.toml`](tools/gh_issue.toml) | A command tool: the `gh` CLI, one argv template, no shell | `.edgar/tools/` |
| [`tools/service_status.toml`](tools/service_status.toml) | An HTTP tool: fixed host, token from the environment | `.edgar/tools/` |
| [`tools/weather.toml`](tools/weather.toml) | An HTTP tool: fixed host, no auth needed | `.edgar/tools/` |
| [`tools/dropbox_ls.toml`](tools/dropbox_ls.toml) | A command tool wrapping `rclone`, so Dropbox's own OAuth stays outside edgar | `.edgar/tools/` |
| [`tools/onedrive_ls.toml`](tools/onedrive_ls.toml) | The same pattern as `dropbox_ls.toml`, for OneDrive | `.edgar/tools/` |
| [`tools/gmail_search.toml`](tools/gmail_search.toml) | A command tool wrapping `gws`, so Google's own OAuth stays outside edgar | `.edgar/tools/` |
| [`tools/gcal_events.toml`](tools/gcal_events.toml) | The same pattern as `gmail_search.toml`, for Calendar | `.edgar/tools/` |
| [`tools/gdocs_get.toml`](tools/gdocs_get.toml) | The same pattern as `gmail_search.toml`, for Docs | `.edgar/tools/` |
| [`tools/web_search.toml`](tools/web_search.toml) | Web search: an HTTP tool in three variants (Brave, Tavily, your own SearXNG) — pick one, there is no default host | `.edgar/tools/` |
| [`skills/changelog/`](skills/changelog/) | A skill: instructions plus a template file beside them | `.edgar/skills/` |
| [`skills/web-research/`](skills/web-research/) | A skill: search, `fetch` the best hits, answer with sources | `.edgar/skills/` |
| [`agents/code-reviewer.md`](agents/code-reviewer.md) | A subagent: one flat file, `read-only` mode, four tools | `.edgar/agents/` |
| [`extensions/audit-log/`](extensions/audit-log/) | An extension: a manifest plus one observation-only hook | `.edgar/extensions/` |

Project folders (`.edgar/…`) apply to one project; the same folders under
`~/.edgar/` apply everywhere. A project's tools run only after `edgar trust`; a
skill is instructions, so it needs no trust; an agent's own tools and mode
still pass through the guard like any other call, but it cannot ask for
anything wider than the mode the calling session is in [PERM-8].

```bash
mkdir -p .edgar/tools .edgar/skills .edgar/agents
cp examples/tools/gh_issue.toml .edgar/tools/
cp -r examples/skills/changelog .edgar/skills/
cp examples/agents/code-reviewer.md .edgar/agents/
edgar trust
edgar tools list
edgar skills list
```

Once an agent file exists, the `task` tool appears on its own; there is no
`edgar agents list` (cut from 1.0, [ADR-0053](../docs/adr/0053-what-1-0-actually-ships.md)) — ask
the model to use `task` with `code-reviewer` and a description of what to
review, and it runs in its own session with its own budget.

Recipes that build on these are in the [Cookbook](../docs/COOKBOOK.md).
