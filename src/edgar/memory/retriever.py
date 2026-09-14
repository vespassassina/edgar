"""The Retriever port: what `recall` searches through [MEM-24, ADR-0024].

The built-in adapter is lexical, FTS5 over facts and past sessions (recall.py). A
plugin may register another, vectors or a graph, under the `edgar.retrievers`
entry point; `[memory] retriever` names the one to use. Whichever runs, it only
reads: a retriever never creates or changes a fact.
"""

# retriever(name):
#   "fts5"                          -> the built-in one
#   a name under edgar.retrievers   -> that plugin, called with the memory and the root
#   anything else                   -> a config error naming what is installed

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol

from edgar.core.errors import ConfigError
from edgar.memory.store import Memory


@dataclass(frozen=True, slots=True)
class Hit:
    kind: str  # "fact" or "turn"
    ref: str  # a fact's id, or "SESSION#TURN"
    scope: str
    text: str


class Retriever(Protocol):
    def search(
        self, terms: list[str], scopes: list[str], kinds: list[str], limit: int
    ) -> list[Hit]:
        """Hits for any of `terms`, best first; the model supplies synonyms as terms."""
        ...


def retriever(name: str, memory: Memory, root: Path) -> Retriever:
    if name == "fts5":
        from edgar.memory.recall import Fts5Retriever  # the adapter, loaded by name

        return Fts5Retriever(memory, root)
    plugins = entry_points(group="edgar.retrievers")
    for plugin in plugins:
        if plugin.name == name:
            made: Retriever = plugin.load()(memory, root)
            return made
    installed = ", ".join(["fts5", *sorted(p.name for p in plugins)])
    raise ConfigError(f"[memory] retriever {name!r} is not installed; there is: {installed}")
