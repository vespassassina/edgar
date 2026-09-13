"""`edgar models list` and the model picker.

`list` prints the model each role resolves to, and every provider with its
endpoint and key variable, without contacting anything, so where prompts go is a
question the config answers [PRV-15]. `edgar models` and `/model` pick a model
interactively [CLI-30, ADR-0034].
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

from edgar.config.load import load, project_config, user_config
from edgar.config.schema import Config
from edgar.core.errors import ConfigError, EdgarError
from edgar.providers.quirks import quirks_for
from edgar.providers.registry import BUILTIN, resolve
from edgar.providers.routing import Role, RoutingContext, select_model

ROLES: tuple[Role, ...] = ("main", "compactor", "controller", "condenser")


def list_models(cwd: Path, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    config = load(cwd, env=env)
    out = sys.stdout
    if config.model.default is None:
        out.write("model: none configured (--model provider/model, or [model] default)\n")
    else:
        for role in ROLES:
            chosen = select_model(RoutingContext(role=role), config.model)
            out.write(f"{role:<11} {chosen.model:<36} {chosen.reason}\n")
    out.write("\n")
    for name in sorted({*BUILTIN, *config.providers} - {"fake"}):
        out.write(f"{name:<11} {_describe(name, config, env)}\n")
    return 0


def _describe(name: str, config: Config, env: Mapping[str, str]) -> str:
    try:
        q = quirks_for(name, config.providers.get(name))
    except ConfigError as exc:
        return f"({exc})"
    url = q.base_url or (
        f"${q.base_url_env}" + ("" if env.get(q.base_url_env or "") else " (unset)")
    )
    key = (
        f"${q.api_key_env} ({'set' if env.get(q.api_key_env) else 'unset'})"
        if q.api_key_env
        else "no key"
    )
    return f"{url:<36} {key}"


# The picker [CLI-30, ADR-0034]


async def pick(
    config: Config,
    env: Mapping[str, str] | None,
    ask: Callable[[str], Awaitable[str]],
    say: Callable[[str], None],
) -> str | None:
    """Provider, then model. The provider's list is fetched only once it is picked,
    and a model name can always be typed instead. Never asks for a key."""
    env = os.environ if env is None else env
    names = sorted({*BUILTIN, *config.providers} - {"fake"})
    say("\n".join(f"{i:>3}. {n:<11} {_describe(n, config, env)}" for i, n in enumerate(names, 1)))
    name = _choose(await ask("provider (number or name, empty to cancel): "), names)
    if name is None:
        return None
    try:
        provider, _ = resolve(f"{name}/-", config, env=env)
    except EdgarError as exc:
        say(f"{exc}" + (f"\nhint: {exc.hint}" if exc.hint else ""))
        return None
    say(f"asking {name} for its models…")
    try:
        models = await provider.models()
    except EdgarError as exc:
        say(f"could not list models: {exc}")
        models = []
    shown = models[:40]
    if shown:
        say("\n".join(f"{i:>3}. {m}" for i, m in enumerate(shown, 1)))
    if len(models) > len(shown):
        say(f"     … and {len(models) - len(shown)} more; type a name")
    answer = await ask("model (number or name, empty to cancel): ")
    model = _choose(answer, models) or answer.strip()
    return f"{name}/{model}" if model else None


def _choose(answer: str, options: Sequence[str]) -> str | None:
    answer = answer.strip()
    if answer.isdigit() and 0 < int(answer) <= len(options):
        return options[int(answer) - 1]
    return answer if answer in options else None


def remember(choice: str, path: Path) -> str:
    """Make `choice` the default: create the file if there is none, otherwise say
    what to add. An existing config is hand-authored and never edited [ADR-0034]."""
    line = f'[model]\ndefault = "{choice}"\n'
    if path.exists():
        return f"{path} exists, so it is left alone. Set this in it:\n\n{line}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line, encoding="utf-8")
    return f"wrote {path}"


def pick_command(cwd: Path, home: Path | None = None) -> int:
    """`edgar models`: pick a model, then optionally make it the default."""
    from prompt_toolkit import PromptSession  # interactive path only (NFR-1)

    config = load(cwd)
    session: PromptSession[str] = PromptSession()

    async def run() -> int:
        choice = await pick(config, None, session.prompt_async, print)
        if choice is None:
            return 0
        where = await session.prompt_async(f"make {choice} the default? [p]roject, [u]ser, [n]o: ")
        target = {"p": project_config(cwd), "u": user_config(home or Path.home())}
        path = target.get(where.strip().lower()[:1])
        print(remember(choice, path) if path else f"not saved; use --model {choice}")
        return 0

    return asyncio.run(run())
