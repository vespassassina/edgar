"""`edgar -p`: one turn, non-interactive [CLI-2].

The result goes to stdout and nothing else does [CLI-5]. Status output, --json and
--events arrive in M4.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from edgar.config.load import load
from edgar.context.prompts import choose_profile, load_prompt, profile_prompt
from edgar.core.errors import ConfigError, UsageError
from edgar.core.events import EventBus, ModelSelected, Subscriber
from edgar.core.loop import Runtime, run_turn
from edgar.core.session import Session
from edgar.providers.registry import resolve, split
from edgar.providers.routing import RoutingContext, select_model
from edgar.tools.registry import core_registry


def run_prompt(
    prompt: str,
    *,
    cwd: Path | None,
    model: str | None,
    mode: str | None,
    subscribers: Iterable[Subscriber] = (),
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> int:
    root = (cwd or Path.cwd()).resolve()
    if not root.is_dir():
        raise UsageError(f"--cwd {root} is not a directory")
    if mode is None:
        # Nobody is there to answer a permission prompt, so the mode must be a
        # decision the caller made, not a default [CLI-9, ADR-0004].
        raise ConfigError(
            "non-interactive runs need an explicit --mode",
            hint="add --mode read-only to look, or --mode ask|auto|yolo",
        )
    flags = {"permissions.mode": (mode, "flag --mode")}
    if model is not None:
        flags["model.default"] = (model, "flag --model")
    config = load(root, home=home, env=env, flags=flags)
    selection = select_model(RoutingContext(), config.model)
    provider, provider_model = resolve(selection.model, config, env=env)
    block = config.providers.get(split(selection.model)[0])
    setting = block.prompt_profile if block and block.prompt_profile else config.prompt.profile
    profile = choose_profile(setting, provider.capabilities.max_context)

    bus = EventBus()
    for subscriber in subscribers:
        bus.subscribe(subscriber)
    bus.emit(ModelSelected(model=selection.model, rule=selection.rule, reason=selection.reason))
    runtime = Runtime(
        provider=provider,
        model=provider_model,
        tools=core_registry(),
        system_prompt=load_prompt(root, profile_prompt(profile)).text,
        bus=bus,
        max_output_tokens=config.tools.max_output_tokens,
    )
    session = Session(cwd=root, model=selection.model, mode=config.permissions.mode)
    result = asyncio.run(run_turn(session, prompt, runtime))
    sys.stdout.write(result.text if result.text.endswith("\n") else result.text + "\n")
    return 0
