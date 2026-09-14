"""Facts as markdown, for `edgar memory edit` [MEM-4].

The file is one section per scope and one line per fact, `- [12] the fact`. The
number ties a line to its fact: change the text and the fact is replaced, delete
the line and it is forgotten, add a line without a number and it is a new fact.
`memory undo` takes the whole edit back.
"""

# render(sections) -> text:
#   a comment saying how to edit, then "## global" and "## project" with their lines
#
# parse(text, scopes) -> {scope: [(id or None, text)]}:
#   "## NAME" picks the scope; "- [N] text" or "- text" is a fact; other lines are ignored
#
# edit(text):
#   write it to a temporary file, open $VISUAL or $EDITOR (notepad on Windows, vi
#   elsewhere), wait for it to close, read the file back

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from edgar.core.errors import UsageError
from edgar.memory.store import Fact

HEADER = """\
<!-- edgar memory. One fact per line. Change a line's text to replace that fact,
delete a line to forget it, add "- text" to remember something new. The facts are
shown to the model as notes, not instructions. `edgar memory undo` reverts the edit. -->
"""
LINE = re.compile(r"^\s*[-*]\s+(?:\[(\d+)\]\s*)?(.*)$")


def render(sections: dict[str, list[Fact]]) -> str:
    parts = [HEADER]
    for name, facts in sections.items():
        parts.append(f"\n## {name}\n\n" + "".join(f"- [{f.id}] {f.text}\n" for f in facts))
    return "".join(parts)


def parse(text: str, scopes: dict[str, str]) -> dict[str, list[tuple[int | None, str]]]:
    """`scopes` maps a section's name to its scope; lines under no section are ignored."""
    wanted: dict[str, list[tuple[int | None, str]]] = {scope: [] for scope in scopes.values()}
    scope = None
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if line.startswith("## "):
            scope = scopes.get(line[3:].strip())
        elif scope and (m := LINE.match(line)):
            wanted[scope].append((int(m[1]) if m[1] else None, m[2].strip()))
    return wanted


def edit(text: str) -> str:
    fallback = "notepad" if os.name == "nt" else "vi"
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or fallback
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "memory.md"
        path.write_text(text, encoding="utf-8")
        # An editor setting may carry flags ("code --wait"); it is split, never run by a shell.
        program, *flags = shlex.split(editor, posix=os.name != "nt")
        argv = [shutil.which(program) or program, *flags, str(path)]  # code.cmd on Windows
        try:
            code = subprocess.call(argv)
        except OSError as exc:
            raise UsageError(f"cannot start the editor {editor!r}: {exc}") from None
        if code != 0:
            raise UsageError(f"the editor exited with {code}; nothing was changed")
        return path.read_text(encoding="utf-8")
