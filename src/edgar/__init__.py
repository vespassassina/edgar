"""edgar as a library. `run()` is the embedding API [EXT-9, ADR-0051]: a thin
async wrapper a supervisor process (many sessions, many projects, permission
prompts answered out of band by its own `asker`) calls instead of the CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from edgar.config.schema import Config, Mode
    from edgar.core.events import Subscriber
    from edgar.core.loop import TurnResult
    from edgar.permissions.guard import Asker

# Kept in step with pyproject.toml by tests/unit/test_version.py. Reading it from
# importlib.metadata instead would cost startup time on every run (NFR-1).
__version__ = "0.1.0"


async def run(
    prompt: str,
    *,
    cwd: Path | None = None,
    config: Config | None = None,
    mode: Mode | None = None,
    model: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    asker: Asker | None = None,
    subscribers: Iterable[Subscriber] = (),
    attached: str | None = None,
    verify: str | None = None,
    project_exec: bool = True,
) -> TurnResult:
    # 1. prepare: layered config, unless the caller already built one.
    # 2. setup: guard, tools, skills, the verify check, the prompt prefix.
    # 3. begin a fresh session; authorise and run one turn on the loop.
    # 4. close what the turn opened, and note what changed for next time.
    # Heavy imports deferred so a bare `import edgar` stays light [NFR-1].
    from dataclasses import replace

    from edgar.cli import trust
    from edgar.cli.setup import (
        authorise_verify,
        begin,
        daily,
        finish,
        prepare,
        setup,
        verify_for_turn,
    )
    from edgar.core.errors import ConfigError
    from edgar.core.events import EventBus
    from edgar.core.loop import run_turn
    from edgar.skills.activate import bodies, matching
    from edgar.tools.mcp.client import close

    if mode is None:
        raise ConfigError(
            "edgar.run() needs an explicit mode",
            hint="nobody is here to answer an unmoded prompt; pass mode=...",
        )
    root = (cwd or Path.cwd()).resolve()
    if config is None:
        root, config = prepare(cwd, model=model, mode=mode, env=env, home=home)
    elif model is not None or mode is not None:
        config = replace(
            config,
            model=replace(config.model, default=model) if model else config.model,
            permissions=replace(config.permissions, mode=mode) if mode else config.permissions,
        )
    if project_exec:
        trust.require(root, config, home or Path.home())  # [PERM-13]
    s = setup(
        root, config, home=home, env=env, verify=verify, project_exec=project_exec, asker=asker
    )
    bus = EventBus()
    for subscriber in subscribers:
        bus.subscribe(subscriber)
    session, rt = begin(s, bus, None)
    hits = matching(s.skills, prompt, ())  # no prior round to read touched paths from
    rt = verify_for_turn(s, rt, hits)
    stdin = [attached] if attached else []
    try:
        rt = daily(s, rt)
        await authorise_verify(rt, session)
        return await run_turn(session, prompt, rt, attached=stdin + bodies(hits))
    finally:
        await close(s.servers)
        finish(s, session, bus)
