# Contributing

edgar is a teaching artifact first and a usable tool second. A contribution is
judged on whether it keeps the code small enough to read, not only on whether it
works.

## Before you write code

1. Read [`AGENTS.md`](AGENTS.md). Its constraints apply to people as much as to
   agents.
2. Find the milestone in [`docs/ROADMAP.md`](docs/ROADMAP.md) and the requirement
   IDs it names in [`docs/PRD.md`](docs/PRD.md).
3. Check the "Never" list at the end of the roadmap and the non-goals in PRD §5.2.
4. If you want to change a decision, open an issue first. A decision that is hard
   to reverse gets an ADR in [`docs/adr/`](docs/adr/).

## Setup

You need [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/).

```bash
uv sync
just check
```

`just check` runs the formatter, the linter, `mypy --strict` and the offline test
suite. It must pass before every commit. The suite never touches the network; a
test that tries fails immediately.

## Pull requests

- One concern per pull request.
- Tests first where the requirement makes the shape clear. Touching compaction,
  permissions, routing, paths or the learning path means adding a property test.
- Docs change in the same commit as the code they describe, never later.
- Conventional commit messages with requirement IDs, for example
  `feat(providers): add anthropic adapter [PRV-2]`.
- Adding a dependency needs its import cost justified in the pull request.

## Security

Do not report vulnerabilities in public issues. See [`SECURITY.md`](SECURITY.md).

## Conduct

Participation is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
