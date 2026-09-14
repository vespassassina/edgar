# Proposals

Changes to hand-authored files that no automated process may make (ADR-0007,
ADR-0008). The maintainer reviews each one and applies it, or deletes it.

- [`AGENTS.md.patch`](AGENTS.md.patch): brings `AGENTS.md` in line with the
  v0.3 and v0.4 revisions (ADRs 0015–0025), the capability broker (ADR-0039) and
  ADR-0040 (pseudocode comments, shallow functions, sensible defaults, every limit
  in lines of code). Apply it from the repository root with
  `git apply docs/proposals/AGENTS.md.patch`, then delete it.
