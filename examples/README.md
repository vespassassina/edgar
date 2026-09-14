# Examples

Files to copy into a project, each one working as it is. Nothing here is loaded
until you copy it.

| Example | What it is | Copy it to |
|---|---|---|
| [`tools/gh_issue.toml`](tools/gh_issue.toml) | A command tool: the `gh` CLI, one argv template, no shell | `.edgar/tools/` |
| [`tools/service_status.toml`](tools/service_status.toml) | An HTTP tool: fixed host, token from the environment | `.edgar/tools/` |
| [`skills/changelog/`](skills/changelog/) | A skill: instructions plus a template file beside them | `.edgar/skills/` |

Project folders (`.edgar/…`) apply to one project; the same folders under
`~/.edgar/` apply everywhere. A project's tools run only after `edgar trust`; a
skill is instructions, so it needs no trust.

```bash
mkdir -p .edgar/tools .edgar/skills
cp examples/tools/gh_issue.toml .edgar/tools/
cp -r examples/skills/changelog .edgar/skills/
edgar trust
edgar tools list
edgar skills list
```

Recipes that build on these are in the [Cookbook](../docs/COOKBOOK.md).
