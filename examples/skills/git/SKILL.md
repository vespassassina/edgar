---
name: git
description: Use when committing work, writing a commit message, or answering what changed in this repository.
---

# Working with git

Needs the four command tools from `examples/tools/` (`git-status`, `git-diff`,
`git-log`, `git-commit`), copied to `.edgar/tools/` and trusted.

## Before you commit

1. `git-status` to see what is staged and what is not.
2. `git-diff` to read the change itself. Commit what you can describe; if the
   diff contains something you did not intend to change, stop and say so.
3. `git-log` with count 20 to see how this repository writes messages, and match
   it. Every repository has a house style and the log is where it lives.

## The message

A short imperative subject: "Add the image block", not "Added" or "Adding". Then
a blank line, then why the change exists — the diff already says what it does.
Wrap the body at about 72 columns. The whole message is one argument to
`git-commit`, newlines and all.

## Repository etiquette

Read `AGENTS.md` (or `CONTRIBUTING.md`, or `CLAUDE.md`) at the repository root
before your first commit in a project and follow it over this file: it may fix
the commit format, require a trailer, forbid touching certain files, or say
which branch work goes on. If it asks for a co-author trailer, add it.

Then:

- Never commit on the default branch unless the project says to. Branch first.
- One commit per idea. If the diff does two things, stage and commit them apart.
- Run the project's check (`just check`, `make test`, whatever it names) before
  committing, and do not commit if it fails.
- Never commit a secret, a `.env`, a key or a token. If you see one in the diff,
  stop and tell the user rather than committing around it.
- Do not push, merge, tag, rebase or amend a pushed commit. Those are the user's
  calls; say the work is ready and let them make it.
