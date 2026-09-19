# edgar.controller is v3, and removable: nothing in Core, v1 or v2 imports it, a test
# proves it, and CI deletes the package and runs the suite below it [NFR-12].
#
# Two ways in, both reached by name from cli/setup.py with importlib, so the import
# graph stays one-way and deleting this folder costs one quiet ModuleNotFoundError
# and nothing else [ADR-0015]:
#
#   attach(bus, ...)   subscribe one session's gate to one session's bus
#   overrides(root)    what an earlier session's approved proposals ask for now
#
# attach() does nothing at all unless [controller] enabled is true. The default is
# false, and that is the positioning, not timidity: a harness that promises no hidden
# calls does not start making one per turn because you upgraded.

from __future__ import annotations

from pathlib import Path

from edgar.config.schema import Config
from edgar.controller.gate import Gate
from edgar.controller.store import Controls
from edgar.core.events import EventBus
from edgar.permissions.guard import Guard


def attach(
    bus: EventBus,
    *,
    root: Path,
    home: Path,
    config: Config,
    guard: Guard,
    window: int = 0,
    session: str = "",
) -> Gate | None:
    """Subscribe the controller to one session's bus, if it is switched on [CTRL-2]."""
    if not config.controller.enabled:
        return None
    gate = Gate(
        config=config,
        root=root,
        home=home,
        guard=guard,
        store=Controls(root / ".edgar" / "controller.db"),
        bus=bus,
        window=window,
        session=session,
    )
    bus.subscribe(gate)
    return gate


def overrides(root: Path) -> dict[str, str]:
    """What the controller changed and a person approved, for this session to start
    under: `{"compact": "0.4500"}`, `{"switch_model": "openai/gpt-5-mini"}` [CTRL-6].

    Derived from the mutation log, so `edgar controller revert ID` is the whole undo
    mechanism and there is no second place for the answer to hide [CTRL-10].
    """
    return Controls(root / ".edgar" / "controller.db").overrides()
