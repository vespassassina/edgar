"""`@path` in a typed prompt attaches that file's text [CLI-3].

The typed line is never rewritten. What the human typed stays exactly as typed,
which is what the learning path is allowed to read (MEM-9); the file's text leaves
here as a plain body that only ever becomes `TextBlock(attached=True)`, and an
attached block is context, never a source of active facts.
"""

# One typed line, in order:
#   1. find every @token that starts a word
#   2. resolve it under the working directory
#   3. refuse: missing, a directory, a credential file, outside the cwd, not text
#   4. read it, and spill it past tools.max_output_tokens the way tool output spills
#   5. hand the bodies back for run_turn(attached=...), which marks them attached
#
# Reading a control file (.edgar/config.toml) is deliberately not refused: the
# permission engine asks about a control file only when a tool would *write* it
# (policy.py), and a read inside the working directory is allowed in every mode.
# Refusing it here would be this file inventing a rule of its own [PERM-1].

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from edgar.permissions.matcher import credential, inside
from edgar.tools.spill import spill

TOKEN = re.compile(r"(?:(?<=\s)|\A)@(\S+)")
ACCEPTS = "@path attaches one text file inside the working directory"


@dataclass(frozen=True, slots=True)
class Attached:
    bodies: tuple[str, ...]  # one per accepted @path, headed by the path as typed
    problems: tuple[str, ...]  # user-facing refusals; the turn does not run


def attach(prompt: str, *, cwd: Path, home: Path, max_tokens: int, blob_dir: Path) -> Attached:
    bodies: list[str] = []
    problems: list[str] = []
    for i, token in enumerate(TOKEN.findall(prompt)):
        path = (cwd / token).resolve()
        refusal = _refuse(token, path, cwd=cwd, home=home)
        if refusal is not None:
            problems.append(refusal)
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # images arrive in M20 [CLI-22]
            problems.append(f"@{token} is not a readable text file. {ACCEPTS}")
            continue
        if "\0" in text:  # decodable, but not something a model should read as text
            problems.append(f"@{token} is not a text file. {ACCEPTS}")
            continue
        out = spill(text, max_tokens=max_tokens, blob_dir=blob_dir, name=f"attach_{i}", root=cwd)
        bodies.append(f"{token}\n{out.text}")
    return Attached(tuple(bodies), tuple(problems))


def _refuse(token: str, path: Path, *, cwd: Path, home: Path) -> str | None:
    # Everything a path can be that is not a text file to attach, said plainly.
    if credential(path, home):
        return f"@{token} holds credentials. {ACCEPTS}"
    if not inside(path, cwd.resolve()):
        return f"@{token} is outside the working directory. {ACCEPTS}"
    if not path.exists():
        return f"@{token}: no such file. {ACCEPTS}"
    if path.is_dir():
        return f"@{token} is a directory. {ACCEPTS}"
    return None
