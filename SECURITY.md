# Security policy

edgar runs a language model that can read files, edit them and run commands on
your machine. A security bug here is a bug in the thing standing between the
model and your system, so reports are welcome and taken seriously.

## Reporting a vulnerability

Report privately through GitHub: **Security → Report a vulnerability** on this
repository. Please do not open a public issue for anything you believe is
exploitable.

Include what you ran, what you expected the harness to stop, and what it did
instead. A transcript (`.edgar/sessions/<id>.jsonl`) or a failing test is the
fastest way to a fix. Remove secrets from anything you attach.

You will get an acknowledgement, then a fix or an explanation. Reporters are
credited in the release notes unless they ask not to be.

## What counts

In scope: anything that lets a model, a tool result, fetched content, a project
you cloned or an extension do more than the rules in
[`docs/BLUEPRINT.md` §7](docs/BLUEPRINT.md#7-permissions) allow. Examples:

- a path that escapes the working directory, or a shell command that slips past a
  deny rule
- an automated component widening permissions ("humans widen, machines tighten")
- untrusted text reaching memory or the learning path
- a request to a host the user did not configure
- project hooks, MCP servers or tools running before `edgar trust`

Known limits are listed in [BLUEPRINT §7.4](docs/BLUEPRINT.md#74-residual-risks).
A report that one of them is worse than described there is in scope too.

## Supported versions

Before 1.0, only the latest release gets fixes.

## Releases

Releases are built in CI and published to PyPI through trusted publishing, with
build attestations. No long-lived upload token exists. Dependencies are locked with
hashes in `uv.lock`.
