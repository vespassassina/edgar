"""`edgar init` and `/init`: a project's first config, AGENTS.md and gitignore."""

# Scaffolded from templates/ and never overwritten [CFG-4]. Also what the REPL
# runs when nothing is configured, so the first ten minutes never dead-end.
#
# 1. AGENTS.md and the .gitignore fragment: written if missing, left alone if not.
# 2. config.toml: left alone if one exists; otherwise the template, with a model
#    picked the same way `edgar models` does when there is somewhere to ask.

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from edgar.config.load import load, project_config
from edgar.config.schema import Config

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
Ask = Callable[[str], Awaitable[str]]


async def run(cwd: Path, config: Config, ask: Ask | None, say: Callable[[str], None]) -> str | None:
    # Returns the model chosen, if any, so a caller with a model already picked
    # but not yet saved (the REPL's own startup picker) can apply it itself.
    say(_scaffold(cwd / "AGENTS.md", "AGENTS.md"))
    say(_gitignore(cwd))
    choice: str | None = None
    if config.model.default is None and ask is not None:
        from edgar.cli.models import pick  # interactive path only (NFR-1)

        choice = await pick(config, None, ask, say)
    dest = project_config(cwd)
    if dest.exists():
        say(f"{dest} exists, left alone")
        return choice
    text = (TEMPLATES / "config.toml").read_text(encoding="utf-8")
    if choice is not None:
        text = text.replace('# default = "provider/model"', f'default = "{choice}"')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    say(f"wrote {dest}")
    return choice


def _scaffold(dest: Path, template: str) -> str:
    if dest.exists():
        return f"{dest} exists, left alone"
    dest.write_text((TEMPLATES / template).read_text(encoding="utf-8"), encoding="utf-8")
    return f"wrote {dest}"


def _gitignore(cwd: Path) -> str:
    dest = cwd / ".gitignore"
    existed = dest.is_file()
    if existed and ".edgar/sessions/" in dest.read_text(encoding="utf-8"):
        return f"{dest} already ignores .edgar/ state, left alone"
    fragment = (TEMPLATES / "gitignore.fragment").read_text(encoding="utf-8")
    with dest.open("a", encoding="utf-8") as f:
        f.write(("\n" if existed else "") + fragment)
    return f"{'updated' if existed else 'wrote'} {dest}"


def command(cwd: Path, home: Path | None = None) -> int:
    import asyncio
    import sys

    home = home or Path.home()
    config = load(cwd, home=home)
    ask: Ask | None = None
    if sys.stdin.isatty():
        from prompt_toolkit import PromptSession  # interactive path only (NFR-1)

        ask = PromptSession[str]().prompt_async
    asyncio.run(run(cwd, config, ask, print))
    return 0
