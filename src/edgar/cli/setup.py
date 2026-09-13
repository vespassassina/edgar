"""What `-p` and the REPL share: config, the model, and the runtime built from them."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from edgar.config.load import load
from edgar.config.schema import Config
from edgar.context.prompts import choose_profile, load_prompt, profile_prompt
from edgar.core.errors import UsageError
from edgar.core.events import EventBus, ModelSelected
from edgar.core.loop import Runtime
from edgar.providers.registry import resolve, split
from edgar.providers.routing import RoutingContext, Selection, select_model
from edgar.tools.registry import core_registry


def prepare(
    cwd: Path | None,
    *,
    model: str | None,
    mode: str | None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[Path, Config]:
    root = (cwd or Path.cwd()).resolve()
    if not root.is_dir():
        raise UsageError(f"--cwd {root} is not a directory")
    flags = {}
    if mode is not None:
        flags["permissions.mode"] = (mode, "flag --mode")
    if model is not None:
        flags["model.default"] = (model, "flag --model")
    return root, load(root, home=home, env=env, flags=flags)


def runtime(
    config: Config,
    root: Path,
    bus: EventBus,
    *,
    env: Mapping[str, str] | None = None,
    choice: Selection | None = None,
) -> Runtime:
    """The runtime for the configured main model, or for `choice` (`/model`)."""
    selection = choice or select_model(RoutingContext(), config.model)
    provider, provider_model = resolve(selection.model, config, env=env)
    block = config.providers.get(split(selection.model)[0])
    setting = block.prompt_profile if block and block.prompt_profile else config.prompt.profile
    profile = choose_profile(setting, provider.capabilities.max_context)
    bus.emit(ModelSelected(model=selection.model, rule=selection.rule, reason=selection.reason))
    return Runtime(
        provider=provider,
        model=provider_model,
        tools=core_registry(),
        system_prompt=load_prompt(root, profile_prompt(profile)).text,
        bus=bus,
        max_output_tokens=config.tools.max_output_tokens,
        name=selection.model,
    )
