---
name: changelog
description: Use when adding an entry to CHANGELOG.md, or when asked what changed for users since the last release.
---

# Writing a changelog entry

1. Read `CHANGELOG.md` and find the `## Unreleased` section. Create it under the
   title if it is missing.
2. Look at what changed: `git log --oneline` since the last version tag, and the
   diff where a commit message is unclear.
3. Keep only what a user notices: a new command or flag, a changed default, a fix
   to behaviour they could have hit. Leave out refactors, tests and docs about the
   code.
4. Write each entry with `template.md` in this skill's folder: one line, what
   changed and why it matters to the user, under `Added`, `Changed` or `Fixed`.
5. Show the entries to the user before writing them to the file.
