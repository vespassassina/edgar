# edgar.learning is v3, and removable: nothing in Core, v1 or v2 imports it, a test
# proves it, and CI deletes the package and runs the suite below it [NFR-12].
#
# The one way in is attach(). cli/setup.py's begin() loads this module by name with
# importlib and calls it, so the import graph stays one-way and deleting the folder
# costs one quiet ModuleNotFoundError and nothing else [ADR-0015].
#
# What attach() subscribes, and why each one is allowed to run:
#
#   Recorder     every run, from the bus. It records; it never writes a fact [MEM-18]
#   Learner      PromptTyped only: one line a human typed -> an active fact [MEM-8]
#   ErrorFacts   ToolFinished.error only: four harness-computed fields -> an active
#                fact after repeats [MEM-22]
#   History      the Recorder's finished run -> a line in history.md [MEM-12]
#
# Nothing here subscribes to anything carrying tool output, fetched content, piped
# stdin or an @path body, because no event carries them [MEM-9, ADR-0017].

from __future__ import annotations

from pathlib import Path

from edgar.core.events import EventBus
from edgar.learning.error_facts import ErrorFacts
from edgar.learning.experience import Experience, Recorder
from edgar.learning.history import History
from edgar.learning.learner import Learner
from edgar.memory.store import Memory


def attach(
    bus: EventBus,
    *,
    root: Path,
    session: str,
    memory: Memory,
    scope: str,
    autolearn: bool = True,
    history: bool = True,
) -> None:
    """Subscribe v3's learning to one session's bus."""
    # 1. Telemetry is not learning: it records what happened and writes no facts,
    #    so it runs whether or not autolearn is on [MEM-18].
    store = Experience(root / ".edgar" / "learning.db")
    sinks = [History(root / ".edgar" / "history.md").append] if history else []
    bus.subscribe(Recorder(store, session=session, sinks=sinks))
    # 2. The two paths that may write an active fact, both on ADR-0017's safe list.
    if autolearn:
        bus.subscribe(Learner(memory, scope=scope, bus=bus))
        bus.subscribe(ErrorFacts(store, memory, scope=scope, bus=bus))
