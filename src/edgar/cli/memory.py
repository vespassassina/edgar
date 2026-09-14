"""`edgar memory list | add [--global] TEXT | edit | review | forget ID | undo` [MEM-4,
MEM-5, MEM-23]: what edgar remembers, shown and changed by a human."""

# Each verb reads or changes the facts of this project and the global scope:
#
#   list      active facts by scope, then pending ones waiting for review
#   add       a fact typed here is active at once, unless it nearly repeats one
#             already there, when it waits for review [MEM-10]
#   edit      the facts as markdown in $EDITOR; the saved file is the new set
#   review    each pending fact in turn: save it, or forget it; Enter forgets
#   forget    one fact, by id
#   undo      the last change, whichever verb made it
#
# Nothing here reaches a model. A change shows in the prompt from the next session.

from __future__ import annotations

import sys
from pathlib import Path

from edgar.cli.setup import open_memory
from edgar.config.load import load
from edgar.memory import markdown
from edgar.memory.store import Fact, Memory, project_scope

USAGE = "usage: edgar memory list | add [--global] TEXT | edit | review | forget ID | undo"


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    memory, scope = open_memory(home, load(cwd, home=home)), project_scope(cwd)
    verb, rest = (argv[0], argv[1:]) if argv else ("list", [])
    if verb == "list" and not rest:
        print(listing(memory, scope, cwd))
    elif verb == "add" and rest:
        where = "global" if rest[0] == "--global" else scope
        print(said(memory.add(" ".join(rest[1:] if where == "global" else rest), where)))
    elif verb == "forget" and len(rest) == 1 and rest[0].isdigit():
        if not memory.forget(int(rest[0])):
            print(f"no active or pending fact {rest[0]}", file=sys.stderr)
            return 1
        print(f"forgot fact {rest[0]}; `edgar memory undo` brings it back")
    elif verb == "undo" and not rest:
        count = memory.undo()
        print(f"undid the last change ({count} facts)" if count else "nothing to undo")
    elif verb == "edit" and not rest:
        names = {"project": scope, "global": "global"}
        shown = {name: memory.facts([s]) for name, s in names.items()}
        edited = markdown.edit(markdown.render(shown))
        count = memory.replace(markdown.parse(edited, names))
        print(f"{count} facts changed" if count else "no change")
    elif verb == "review" and not rest:
        return _review(memory, scope)
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0


def listing(memory: Memory, scope: str, root: Path) -> str:
    rows = []
    for title, where, status in (
        (f"project ({root})", [scope], "active"),
        ("global", ["global"], "active"),
        ("pending, for `edgar memory review`", [scope, "global"], "pending"),
    ):
        facts = memory.facts(where, (status,))
        if facts:
            rows += [f"{title}:", *(f"  [{f.id}] {f.text}" for f in facts)]
    return "\n".join(rows) or "nothing remembered yet; /remember TEXT or `edgar memory add`"


def said(fact: Fact) -> str:
    # What adding a fact did, in the words /remember and `memory add` both print.
    if fact.status == "pending":
        return (
            f"fact {fact.id} is close to fact {fact.supersedes} but differs, so it waits: "
            "`edgar memory review` keeps one of them"
        )
    return f"remembered as fact {fact.id}; in the prompt from the next session"


def _review(memory: Memory, scope: str) -> int:
    pending = memory.facts([scope, "global"], ("pending",))
    if not pending:
        print("nothing waiting for review")
        return 0
    for fact in pending:
        replaces = f" (replaces fact {fact.supersedes})" if fact.supersedes else ""
        try:
            answer = input(f'[{fact.id}] "{fact.text}"{replaces}\nsave? [y/N] ').strip().lower()
        except EOFError:  # no terminal to answer from: leave the rest waiting
            return 1
        if answer.startswith("y"):
            memory.confirm([fact.id])
        else:
            memory.forget(fact.id)
    return 0
