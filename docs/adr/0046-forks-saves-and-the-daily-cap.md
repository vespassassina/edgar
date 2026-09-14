# ADR-0046 — Forks, saved sessions and the daily cap, as built

**Status:** Accepted · 2026-09-14 · Completes M7; refines ADR-0010, ADR-0037 and ADR-0038

## Context

The second half of M7 built what ADR-0037 and ADR-0038 moved out of Core: session
forks (`/fork`, `--fork ID[@TURN]`, CLI-22), `/save` and loading a saved file
(`/load PATH`, `--load PATH`, CLI-25), `/history` (CLI-25), the daily cost cap
(BUD-2) and `edgar cost` (BUD-6). It cost 176 lines of code; `src/` is at 5,802 of
v1's 8,000. The spec named the commands and left the mechanics open.

## Options and decisions

**1. What a fork is on disk.** (A) Copy the parent's lines up to the fork point
into a new file. (B) A new file whose second line is `{"type": "fork", "parent":
ID, "at_turn": N}`; reading it reads the parent's lines up to the end of turn N,
then its own. **Decided: B.** A fork costs one line, the parent is never touched,
and a fork of a fork resolves the same way (`chain()`, a loop up the parents and
back down, no recursion). The cost: a fork depends on its parent's file, so
`edgar sessions rm` refuses a session that still has forks and names them.

**2. What "turn N" means.** A turn is counted by the `TurnFinished` events in the
record, the same count `edgar sessions list` shows. Turn 0 is before the first
turn; the default is the parent's latest. Undone turns still count, because the
record never forgets them; forking at a turn that was undone gives the
conversation as it was then, which is what a fork is for.

**3. What `/save` writes.** (A) The raw file. (B) The chain as one file, spilled
tool output read back into the result it came from, and every string redacted
with MEM-15's patterns. **Decided: B.** A saved file is meant to travel: it must
load on another machine without the blobs, and a key pasted into a prompt must not
travel with it. Redaction is applied string by string after parsing, never to the
JSON text, so a pattern cannot run across JSON syntax. It is a pattern list, so the
message after saving still says to check before sharing.

**4. How a saved file opens.** `/load PATH` and `--load PATH` copy its lines into a
new session of the current project (`adopt()`), then open it the way `--resume`
does. The saved file's session id and working directory are not reused: the copy
belongs here. `--fork` and `--load` make the new file and hand its id to the
`--resume` path, so there is one way a session is opened.

**5. `/history`.** The whole conversation from the record, compacted and undone
turns included, the same reader as `edgar sessions show`. The view the model sees
is unchanged.

**6. Where the day's spend lives.** (A) Sum the session files of every project:
no new state, but there is no list of projects to sum. (B) A `spend(day, cost)`
table in `~/.edgar/edgar.db`, beside trust. **Decided: B.** One row per top-level
turn with a known cost, under the local date. A subagent's turn is not added,
because its parent's turn already carries its cost (BUD-4).

**7. How the daily cap is enforced.** (A) A third cap in the loop. (B) Before each
turn, what is left of `daily_cost_cap` today becomes that turn's
`turn_cost_cap` (the smaller of the two), and with nothing left the turn does not
start: `BudgetExceeded`, exit 6. **Decided: B.** The loop already stops cleanly on
a turn cap between requests, with a partial result (BUD-3), so `core/loop.py` is
unchanged. Unknown pricing works as it does for the other caps (BUD-5): a turn
whose cost is unknown cannot be checked against a cap, so with a daily cap set it
stops after its first request, and it adds nothing to the day's spend.
`edgar cost` says so.

## Consequences

- `edgar sessions rm` refuses a parent with forks; remove the forks first.
- A saved file is redacted by patterns, not proven clean.
- The daily cap is per user, across projects, by local date.
- M7 is complete: its "done when" is met by `tests/integration/test_remembering.py`,
  and the forks, saves and cap by `tests/integration/test_forks.py`.
