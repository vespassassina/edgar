"""`edgar init` and `/init`: a project's first config, AGENTS.md and gitignore."""

# Scaffolded from templates/ and never overwritten [CFG-4]. Also what the REPL
# runs when nothing is configured, so the first ten minutes never dead-end.
#
# 1. AGENTS.md and the .gitignore fragment: written if missing, left alone if not.
# 2. config.toml: left alone if one exists; otherwise the template, with a model
#    picked the same way `edgar models` does when there is somewhere to ask, a
#    provider block for a vendor from the catalog, and the answers to a few
#    questions (each one: Enter keeps the default, which stays a comment).
# 3. Tools offered from templates/tools/ (git, web search): copied into
#    .edgar/tools/ on a yes, never over a file that is there, never unasked; one
#    search provider among six, or none.

from __future__ import annotations

import json
import tomllib
from collections.abc import Awaitable, Callable
from pathlib import Path

from edgar.config.load import load, project_config
from edgar.config.schema import Config

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
Ask = Callable[[str], Awaitable[str]]


def _read(raw: str, kind: str) -> str | None:
    if kind == "money":
        try:
            return repr(float(raw)) if float(raw) > 0 else None
        except ValueError:
            return None
    return json.dumps(raw) if kind == "text" or raw in kind.split("|") else None


async def run(
    cwd: Path,
    config: Config,
    ask: Ask | None,
    say: Callable[[str], None],
    home: Path | None = None,
) -> str | None:
    # Returns the model chosen, if any, so a caller with a model already picked
    # but not yet saved (the REPL's own startup picker) can apply it itself.
    say(_scaffold(cwd / "AGENTS.md", "AGENTS.md"))
    say(_gitignore(cwd))
    choice: str | None = None
    if config.model.default is None and ask is not None:
        from edgar.cli.models import pick  # interactive path only (NFR-1)

        choice = await pick(config, None, ask, say)
        if choice is not None and home is not None:
            # Saved for every project, so no other directory asks again [ADR-0073].
            from edgar.cli.models import remember
            from edgar.config.load import user_config

            say(remember(choice, user_config(home)))
    dest = project_config(cwd)
    if dest.exists():
        say(f"{dest} exists, left alone")
        await _tools(cwd, ask, say)
        return choice
    text = (TEMPLATES / "config.toml").read_text(encoding="utf-8")
    if choice is not None:
        text = text.replace('# default = "provider/model"', f'default = "{choice}"')
        text += _vendor_block(choice.split("/")[0])
    for q in tomllib.loads((TEMPLATES / "wizard.toml").read_text("utf-8"))["question"]:
        raw = (await ask(q["ask"])).strip() if ask is not None else ""
        value = _read(raw, q["kind"]) if raw else None
        if raw and value is None:
            say(f"{raw!r} not understood, kept the default")
        elif value is not None:
            text = text.replace(q["marker"], f"{q['key']} = {value}", 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    say(f"wrote {dest}")
    await _tools(cwd, ask, say)
    return choice


async def _tools(cwd: Path, ask: Ask | None, say: Callable[[str], None]) -> None:
    # 1. Offer each bundle whose files are not all there already; with nobody to
    #    ask, offer nothing: an executable file is never written unasked.
    if ask is None:
        return
    folder = cwd / ".edgar" / "tools"
    wrote = False
    for t in tomllib.loads((TEMPLATES / "wizard.toml").read_text("utf-8"))["tool"]:
        todo = [f for f in t["files"] if not (folder / f"{f}.toml").exists()]
        if not todo:
            continue
        # 2. Enter takes the bundle's default; anything else that starts with y is yes.
        raw = (await ask(t["ask"])).strip().lower()
        if not (raw[:1] == "y" if raw else t["default"]):
            continue
        folder.mkdir(parents=True, exist_ok=True)
        for f in todo:
            (folder / f"{f}.toml").write_text(
                (TEMPLATES / "tools" / f"{f}.toml").read_text(encoding="utf-8"), encoding="utf-8"
            )
        say(f"wrote {', '.join(todo)} in {folder}")
        wrote = True
    wrote = await _search(folder, ask, say) or wrote
    if wrote:
        say("they run once you trust this project: `edgar trust`")


async def _search(folder: Path, ask: Ask, say: Callable[[str], None]) -> bool:
    # One provider or none; an existing web_search.toml is the user's and stays.
    dest = folder / "web_search.toml"
    q = tomllib.loads((TEMPLATES / "wizard.toml").read_text("utf-8"))["search"]
    if dest.exists():
        return False
    pick = (await ask(q["ask"])).strip().lower()
    if pick not in q["providers"]:
        return False
    folder.mkdir(parents=True, exist_ok=True)
    dest.write_text((TEMPLATES / "tools" / "search" / f"{pick}.toml").read_text("utf-8"), "utf-8")
    say(f"wrote {dest}; set {q['providers'][pick]} before you search")
    return True


def _vendor_block(name: str) -> str:
    from edgar.cli.models import catalog  # interactive path only (NFR-1)

    row = catalog().get(name, {})
    return (
        f"\n[providers.{name}]\n" + "".join(f'{k} = "{v}"\n' for k, v in row.items()) if row else ""
    )


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
