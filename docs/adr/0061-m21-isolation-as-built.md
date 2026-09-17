# ADR-0061 — M21, isolation as built

**Status:** Accepted · 2026-09-17 · Completes M21; changes the `Sandbox` protocol
designed in [BLUEPRINT §7.5](../BLUEPRINT.md); follows
[ADR-0060](0060-m20-seeing-and-searching-as-built.md); extends
[ADR-0054](0054-m9-subagents-as-built.md)'s subagents with `isolation: worktree`

## Context

M21 adds the two containments edgar had designed but never built: a git worktree
per write-capable subagent [SUB-11], and a real OS sandbox around a shell call
[PERM-15]. Both are the kind of feature where the dangerous failure is not "it
does not work" but "it silently does less than it says", which is worse than not
having it, because it buys a false sense of safety. Every judgement call below
was therefore resolved towards refusing loudly.

`just loc` reads **8,869 of 9,500** after M21: **277 lines of code added** against
the ~350 estimated, leaving 631 for M22.

**Four decisions below are flagged for extra human review before merge:** the
`wrap` protocol (1), what the sandbox boundary actually is (2), what "kept and
named" leaves behind (3), and what was and was not tested for real (6).

## Options and decisions

### 1. The `Sandbox` port returns argv instead of running the process — FLAGGED FOR EXTRA SCRUTINY

BLUEPRINT §7.5 designed `async run(argv, *, cwd, env, writable, network, timeout_s)
-> ProcessResult`. As built, the protocol is pure:

```python
def wrap(self, argv, *, cwd, writable, network) -> list[str]: ...
```

Considered:

- **`async run(...)`, as designed.** Rejected. It makes every backend a second
  process launcher, and `run_argv` is the one place in edgar that starts a
  subprocess in its own group and kills the group on cancellation or timeout.
  Three backends would each have had to re-implement that, and a Ctrl-C bug in
  one of them would be invisible until someone pressed Ctrl-C on that platform.
- **`wrap(...) -> list[str]`, chosen.** One launcher keeps one cancellation
  story. It also makes the backends testable: a bwrap argv and a seatbelt
  profile are strings, so `tests/unit/test_sandbox.py` asserts both on *every*
  platform, including the macOS machine that cannot run bwrap. Most of what goes
  wrong in a sandbox is a wrong or missing flag, and that is precisely what a
  string assertion catches.

Cost: a backend that is not expressible as "prefix this argv" cannot use this
port. `docker run …` is expressible, so `container` is unaffected. A backend that
needed to supervise the process, stream into it, or clean up afterwards would
need the port widened, and that widening should happen in the open rather than by
adding an escape hatch now.

BLUEPRINT §7.5 is edited in the same commit. Deviating from the spec silently was
not an option; the rule is to change the doc and the code together.

### 2. The sandbox is a write and network boundary, not a read boundary — FLAGGED FOR EXTRA SCRUTINY

**The specs contradict each other and someone has to decide.** ROADMAP M21 says
the test is that "a `shell` call **cannot read** outside the allowed roots and
cannot reach the network when the decision says no". BLUEPRINT §7.5 specifies
bubblewrap with a **read-only root** and the project and blob dirs writable, and
PRD PERM-15 names only writable directories and the network. The Blueprint's
design does not produce the Roadmap's test: `--ro-bind / /` means everything is
readable and nothing but the named roots is writable.

Considered:

- **Build a read boundary anyway** (an allowlist of readable paths). Rejected on
  two grounds. It is a different and much larger design — every interpreter,
  shared library, certificate store and toolchain a command needs would have to
  be enumerated per platform, or nothing runs — and it was never specified, so it
  would be a milestone's worth of unreviewed security design smuggled in under an
  estimate of ~200 lines.
- **Ship the designed write+network boundary and claim the read boundary
  anyway.** Rejected outright. This is the exact failure the milestone exists to
  prevent.
- **Ship the designed write+network boundary and say plainly that reads are not
  confined.** Chosen. It is written in BLUEPRINT §7.5, in the ROADMAP row, in the
  tour's stop 3 in the same words, and here.

**What a reviewer should decide:** whether a read boundary is wanted at all. If
it is, it is its own milestone with its own design, not a patch to these fifty
lines. Until then, a confined process can read everything the user can read, and
the honest summary of `[shell] sandbox` is: *it cannot write outside your project
and it cannot open a socket when the permission engine said no.*

### 3. A dirty worktree is kept, and what "kept" leaves behind — FLAGGED FOR EXTRA SCRUTINY

The roadmap says `remove` when clean, `keep` when dirty, both announced. As built:

- `finish()` runs `git status --porcelain` in the tree. **Anything at all** —
  including a single untracked file — counts as dirty and the worktree is kept.
- `git worktree remove` is called from the parent repository and **never** with
  `--force`. If git itself objects for a reason edgar did not anticipate, the
  tree survives and git's own message is reported.
- Nothing is ever deleted to make room, and no cleanup runs on a later session.

**What "kept and named" actually produces**, which a reviewer should check against
what they expect:

| Question | Answer |
|---|---|
| Where does it live? | `<repo>/.edgar/worktrees/<agent>-<session>` |
| What is the branch? | `edgar/<agent>-<session>`, which survives removal either way |
| How is it announced? | Appended to the `task` tool's result: the path, the branch, the diff stat, and the literal `git worktree remove <path>` line |
| Where is that seen? | The model reads it as the tool result; the human reads it in the transcript, and it is in the session's JSONL |
| How does someone find it a week later? | `git worktree list` and `git branch --list 'edgar/*'` both still show it. There is no separate registry, no log file and no notification |

That last row is the weak point and is stated rather than hidden: a human who
does not scroll back and does not run `git worktree list` will not learn about a
kept tree on their own. The alternatives considered were a `.edgar/` manifest
file (a second source of truth that git already maintains, and one more thing to
go stale) and a startup warning (noise on every session for something that is
usually deliberate). Neither was built. If a reviewer wants discovery, the cheap
version is a line in `edgar doctor` in M22.

`.edgar/worktrees/` is added to `templates/gitignore.fragment`. Without `.edgar/`
ignored, a worktree always reads dirty (the session's own state is inside it) and
is therefore always kept: safe, but useless. That is a real precondition and is
called out here.

### 4. `git worktree add` failing, and the parent's own uncommitted work

**Failure.** `create()` returns `(None, refusal)` and `spawn()` returns that
refusal as a validation error **without starting the agent at all**. There is no
fallback to running unisolated. An agent whose author wrote `isolation: worktree`
and silently got a shared tree is worse than an agent that did not run. The two
refusals are: not inside a git repository (checked with `rev-parse
--show-toplevel` first, so the message says so plainly), and any non-zero exit
from `git worktree add`, whose own stderr is passed through. `git` missing from
`PATH` is caught as `FileNotFoundError` and reported as exit 127 with that text.

**The parent's uncommitted changes.** A worktree is cut from `HEAD` — the
*commit*, never the index or the working tree — so a human halfway through an
edit when a subagent starts is not at risk: the subagent cannot see that edit and
cannot touch it. This was verified against real `git` before the code was written
and is asserted by a test named after the fact rather than after the function.
Uncommitted parent work therefore neither blocks worktree creation nor leaks into
it, and `git worktree add` is never passed `--force` or `-f` under any condition.

### 5. An unavailable backend ends the session

`backend(name)` raises `ConfigError` both for a name that does not exist and for
one that is merely not installed on this machine, with a hint naming `best()`.
The alternative — falling back to `none` with a warning — was rejected: a warning
scrolls past, and the session then runs every command unconfined under a config
file that says `bwrap`. `container` is in `BACKENDS` for the config's own
validation but has no adapter, so asking for it fails with "not built yet"
rather than being quietly accepted.

`edgar doctor` prints the configured backend, the best available one, and advice.
It never changes the setting: turning a sandbox on is a policy change, and
machines do not widen *or* narrow policy on their own (invariant 2).

### 6. What was verified for real, and what was not — FLAGGED FOR EXTRA SCRUTINY

The build machine is macOS (darwin 25.6.0). Stated plainly:

| Backend | Status |
|---|---|
| `none` | Exercised. Trivially. |
| `seatbelt` | **Executed for real.** Two tests run a confined `shell` call: a write inside the project succeeds, a write outside is refused with "Operation not permitted", and a socket cannot be opened when the decision said no. Also probed by hand with `sandbox-exec` before the code was written. |
| `bwrap` | **Written but never executed.** Its argv is asserted on every platform (read-only root bind, the writable binds, `--unshare-net` present only when the network was refused, `--chdir`, the `--` terminator, and a missing bind source skipped because bwrap refuses to start on one). The flags were chosen from bubblewrap's documented behaviour. **Nobody has run it.** |
| `container` | Not built. |

So: bwrap is verified to the extent that its command line is what a reader of
`bwrap(1)` would expect, and no further. It has never confined a process in this
repository's history. **A Linux reviewer should run the two seatbelt tests'
equivalents against bwrap before anyone relies on it.** The roadmap's own "done
when" asks for a dogfood day on macOS *and* Linux; only the macOS half is done.

### 7. Two smaller calls, recorded because they touch policy

**Control files inside a worktree.** `permissions/control.py`'s `is_control` now
answers the same way for an `.edgar/` anywhere under the tree, not only the
project's own. Without it, a subagent's worktree would contain a second,
unguarded copy of the files that steer edgar. This only ever *adds* an Ask, so it
tightens. Consciously left out: instruction prose (`AGENTS.md` and friends) at a
worktree root is not control-protected. The line drawn is that `.edgar/config.toml`
and the `tools/`, `agents/`, `skills/`, `prompts/` and `extensions/` trees are the
policy surface; prose is not.

**The verify command keeps the network.** A check runs confined for writes but
with the network allowed, because it is a command a human declared in config, not
one a model chose, and `just check`-shaped commands routinely need to resolve
dependencies. A reviewer who disagrees should say so; it is one boolean in
`core/verify.py`.

## Consequences

- `sandbox/` is 111 lines of code for four files, and `agents/worktree.py` is 59.
  The whole milestone is 277, which is 73 under estimate.
- `[shell] sandbox` still defaults to `none`, so nothing changes for anyone who
  does not opt in. `edgar doctor` is where they learn they could.
- The templates' `config.toml` is **not** edited here: it is hand-authored
  (ADR-0008), so the proposed `sandbox` line is written into `docs/HANDOFF.md`
  for the maintainer to apply.
- `container` remains Past v4. It was not built speculatively, and the `wrap`
  port is the shape it would use.
