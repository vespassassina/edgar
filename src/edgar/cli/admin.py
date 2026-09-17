"""The subcommands that look at a project rather than run a turn."""

# `edgar trust`, `edgar permissions list|revoke` [PERM-6, PERM-13, CLI-19];
# `edgar sessions list|show|rm` [CLI-11]; `edgar cost` [BUD-6]; `edgar mcp
# list|test NAME` [TOOL-7]; `edgar tools list|describe` and `edgar skills
# list|validate` [SKL-7]; `edgar init` [CFG-4]; `edgar doctor` [CFG-5].
#
# Each subcommand is one branch of command(): read what is on disk, print it, and
# return the exit code. None of them contacts a model. Only `trust`, `revoke` and
# `sessions rm` change anything, and each changes only what it names; `rm` keeps a
# session while a fork still reads its file.

from __future__ import annotations

import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from edgar.agents.spawn import subagents_config
from edgar.cli import trust
from edgar.cli.setup import spending, toolset
from edgar.config.load import load
from edgar.context.tokens import message_text
from edgar.core.errors import UsageError
from edgar.permissions.guard import Guard
from edgar.permissions.policy import Policy
from edgar.skills.discovery import lint
from edgar.storage.db import Store
from edgar.storage.transcript import conversation, find, forks, listing
from edgar.tools.builtin.task import TaskTool
from edgar.tools.mcp.client import FAILURES, Server, close
from edgar.tools.mcp.schema import hints

USAGE = """usage: edgar init | edgar doctor
       edgar trust [--yes] | edgar permissions list | edgar permissions revoke ID
       edgar sessions list | show ID | rm ID | compact ID
       edgar tools list | describe NAME | edgar skills list | validate | edgar cost
       edgar mcp list | test NAME | login NAME | logout NAME
       edgar ext list | edgar login PROVIDER | edgar logout PROVIDER
       edgar context show [SESSION] | edgar config show --resolved"""


def command(argv: list[str], cwd: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    if argv == ["init"]:
        from edgar.cli.init import command as init_command

        return init_command(cwd, home)
    if argv == ["doctor"]:
        from edgar.cli.doctor import command as doctor_command

        return doctor_command(cwd, home)
    if argv[0] == "config":
        from edgar.cli.inspect import config_show  # the layered config and its origins

        return config_show(argv[1:], cwd, home)
    if argv[0] == "context":
        from edgar.cli.inspect import context_show  # the builder and a session record

        return context_show(argv[1:], cwd, home)
    if argv == ["cost"]:
        return _cost(cwd, home)
    if argv[0] == "mcp" and len(argv) in (2, 3):
        return _mcp(argv, cwd, home)
    if argv[0] in ("login", "logout") and len(argv) == 2:
        return _sign_in(argv[0], argv[1])
    if argv[:2] == ["sessions", "compact"] and len(argv) == 3:
        from edgar.cli.inspect import sessions_compact  # the loop's own compaction

        return sessions_compact(argv[2], cwd, home)
    if argv[0] == "sessions" and len(argv) in (2, 3):
        return _sessions(argv[1:], cwd)
    if argv[0] in ("tools", "skills") and len(argv) in (2, 3):
        return _tools(argv, cwd, home)
    if argv == ["ext", "list"]:
        return _ext(cwd, home)
    if argv[0] == "trust" and set(argv[1:]) <= {"--yes"}:
        config = load(cwd, home=home)
        if not trust.executable(cwd, config):
            print("nothing to trust: this project declares no executable config")
            return 0
        print(trust.describe(cwd, config))
        if "--yes" not in argv and input("trust it? [y/N] ").strip().lower() != "y":
            return 1
        trust.trust(cwd, config, home)
        print(f"trusted {cwd}; a change to that config asks again")
        return 0
    grants = Store(cwd / ".edgar" / "edgar.db")
    if argv[1:] == ["list"]:
        for grant_id, tool, subject, created in grants.grants():
            when = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M")
            print(f"{grant_id:>4}  {when}  {tool:<10} {subject}")
        return 0
    if len(argv) == 3 and argv[1] == "revoke" and argv[2].isdigit():
        if grants.revoke(int(argv[2])):
            print(f"revoked {argv[2]}")
            return 0
        print(f"no grant {argv[2]}", file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


def _sessions(argv: list[str], cwd: Path) -> int:
    if argv == ["list"]:
        print("\n".join(listing(cwd)) or "no sessions yet")
    elif argv[0] == "show" and len(argv) == 2:
        for message in conversation(find(cwd, argv[1])):
            print(f"{message.role}: {message_text(message)}\n")
    elif argv[0] == "rm" and len(argv) == 2:
        path = find(cwd, argv[1])
        if children := forks(path):  # they read this file, so it stays while they do
            raise UsageError(
                f"{path.stem} has forks: {', '.join(children)}", hint="remove those first"
            )
        shutil.rmtree(path.with_suffix(""), ignore_errors=True)  # its blobs
        path.unlink()
        print(f"removed {path.stem}")
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0


def _cost(cwd: Path, home: Path) -> int:
    # Every project's spend, by day; a turn whose price was unknown is not in it.
    cap = load(cwd, home=home).budget.daily_cost_cap
    days = dict(spending(home).spent(7))
    today = days.get(date.today().isoformat(), 0.0)
    limit = f" of daily_cost_cap ${cap:.2f}" if cap is not None else "; no daily_cost_cap set"
    print(f"today ${today:.4f}{limit}")
    for day, cost in days.items():
        print(f"  {day}  ${cost:.4f}")
    print("turns priced as unknown are not counted (see /cost in a session)")
    return 0


def _sign_in(what: str, name: str) -> int:
    # `edgar login PROVIDER` for a provider that issues a key through the browser
    # [PRV-18]. The keyring holds it; nothing is written to a config file [CFG-6].
    import asyncio

    from edgar.auth import keys
    from edgar.providers.quirks import quirks_for

    if what == "logout":
        print(f"signed out of {name}" if keys.logout(name) else f"nothing stored for {name}")
        return 0
    row = quirks_for(name, None).oauth
    if row is None:
        raise UsageError(
            f"{name} does not issue keys through a browser",
            hint="set its API key variable, or api_key_command in ~/.edgar/config.toml",
        )
    asyncio.run(keys.login(name, row, print))
    return 0


def _mcp_sign_in(what: str, found: list[Server]) -> int:
    # The same for a remote MCP server, whose token is discovered from what the
    # server publishes [ADR-0032]. A turn never opens a browser; this does.
    import asyncio

    from edgar.auth import mcp as mcp_auth

    server = found[0]
    if server.local:
        raise UsageError(f"{server.name} is a local program", hint="it needs no sign-in")
    url = server.block.url or ""
    if what == "logout":
        print(f"signed out of {url}" if mcp_auth.forget(url) else f"nothing stored for {url}")
        return 0
    asyncio.run(mcp_auth.sign_in(url, print))
    return 0


def _mcp(argv: list[str], cwd: Path, home: Path) -> int:
    # The one place that starts every configured server: `list` to see what a
    # session would get, `test NAME` to try one. Each answer is cached, so the
    # next session knows the tools without starting anything [TOOL-8].
    import asyncio

    config = load(cwd, home=home)
    trusted = trust.trusted(cwd, config, home)
    _, _, found, _, _ = toolset(cwd, home, config, project_exec=trusted)
    if argv[1] in ("test", "login", "logout") and len(argv) == 3:
        found = [s for s in found if s.name == argv[2]]
        if not found:
            raise UsageError(f"no MCP server {argv[2]!r}", hint="edgar mcp list shows them")
        if argv[1] != "test":
            return _mcp_sign_in(argv[1], found)
    elif argv[1:] != ["list"]:
        print(USAGE, file=sys.stderr)
        return 2
    if not found:
        print("no MCP servers; add one as [mcp.NAME] in .edgar/config.toml")
        return 0
    return asyncio.run(_ask(found))


async def _ask(found: list[Server]) -> int:
    failed = 0
    for server in found:
        kind = "stdio" if server.local else "http"
        try:
            tools = await server.discover()
        except FAILURES as exc:
            print(f"{server.name}  {kind}  {server.where}  failed: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{server.name}  {kind}  {server.where}  {len(tools)} tools")
        for tool in tools:
            # What the server claims about a tool is shown, never used [TOOL-13].
            said = hints(tool.raw)
            first = tool.schema.description.splitlines()[:1]
            print(f"  {tool.schema.name:<44} {first[0][:60] if first else ''} {said}".rstrip())
    await close(found)
    return 1 if failed else 0


def _tools(argv: list[str], cwd: Path, home: Path) -> int:
    # What a session here would get: project tools only once the project is trusted,
    # and `task` only when there is an agent file to run, exactly as `setup()` decides.
    config = load(cwd, home=home)
    trusted = trust.trusted(cwd, config, home)
    tools, found, _, agents, ext = toolset(cwd, home, config, project_exec=trusted)
    if agents.agents:
        policy = Policy(mode=config.permissions.mode, cwd=cwd, home=home.resolve())
        guard = Guard(policy, store=Store(cwd / ".edgar" / "edgar.db"))
        limits = subagents_config(config.later)
        tools.add([TaskTool(agents.agents, tools, guard, config, None, limits)])
    problems = [*tools.warnings, *found.warnings, *found.problems]
    problems += [*agents.warnings, *agents.problems, *ext.warnings, *ext.problems]
    for line in problems:
        print(f"warning: {line}", file=sys.stderr)
    if argv[1:] == ["list"] and argv[0] == "tools":
        for t in tools.schemas():
            print(f"{t.name:<16} {t.kind:<8} {t.origin:<8} {t.description.splitlines()[0]}")
    elif argv[1] == "describe" and len(argv) == 3 and (tool := tools.get(argv[2])):
        fields = ("name", "description", "kind", "origin", "category", "read_only")
        shown = {k: getattr(tool.schema, k) for k in fields}
        print(json.dumps({**shown, "input": tool.schema.input_schema}, indent=2))
    elif argv[1:] == ["list"]:
        for s in found.skills.values():
            print(f"{s.name:<24} {s.origin:<16} {s.description}")
        if not found.skills:
            print("no skills; add one as .edgar/skills/NAME/SKILL.md")
    elif argv[1:] == ["validate"] and argv[0] == "skills":
        lints = [warn for s in found.skills.values() if (warn := lint(s))]
        for warn in lints:
            print(f"warning: {warn}", file=sys.stderr)
        print(f"{len(found.skills)} skills ok, {len(found.problems)} with problems")
        return 1 if found.problems else 0
    else:
        print(USAGE, file=sys.stderr)
        return 2
    return 0


def _ext(cwd: Path, home: Path) -> int:
    # `edgar ext list`: every extension a session here would load, and what it
    # brought [EXT-2].
    config = load(cwd, home=home)
    trusted = trust.trusted(cwd, config, home)
    _, _, _, _, ext = toolset(cwd, home, config, project_exec=trusted)
    for line in [*ext.warnings, *ext.problems]:
        print(f"warning: {line}", file=sys.stderr)
    for manifest in ext.extensions.values():
        print(f"{manifest.name:<24} {manifest.version:<10} {manifest.description}")
    if not ext.extensions:
        print("no extensions; add one as .edgar/extensions/NAME/extension.toml")
    return 0
