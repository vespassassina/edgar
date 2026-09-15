from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import get_args

from edgar import __version__
from edgar.config.schema import Mode
from edgar.core.errors import EdgarError

# Nothing heavy may be imported at module level here: this module is on the path of
# every run, and tests/e2e/test_startup.py fails the build if httpx, rich,
# prompt_toolkit, jsonschema, yaml, keyring or any edgar.providers module is pulled
# in (NFR-1, ADR-0012). The run paths are imported inside main().

# The subcommands that look at a project rather than run a turn (cli/admin.py).
ADMIN = {"trust", "permissions", "sessions", "tools", "skills", "cost", "mcp", "login", "logout"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar",
        description="The agent harness you can read in an afternoon.",
        epilog="Other commands: edgar models [list], edgar trust, "
        "edgar permissions list|revoke ID, edgar prompt show, "
        "edgar sessions list|show ID|rm ID, edgar tools list|describe NAME, "
        "edgar skills list|validate, edgar memory list|add|edit|review|forget ID|undo, "
        "edgar cost, edgar mcp list|test|login|logout NAME, "
        "edgar login PROVIDER, edgar logout PROVIDER",
    )
    parser.add_argument("--version", action="version", version=f"edgar {__version__}")
    parser.add_argument("-p", "--prompt", help="run one turn non-interactively and exit")
    parser.add_argument("--model", help="provider/model, for example fake/test")
    parser.add_argument("--mode", choices=get_args(Mode), help="permission mode; required with -p")
    parser.add_argument("--cwd", type=Path, help="working directory (default: here)")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="with -p: one JSON object")
    output.add_argument("--events", action="store_true", help="with -p: events as JSON Lines")
    again = parser.add_mutually_exclusive_group()
    again.add_argument("--resume", nargs="?", const="", metavar="ID", help="reopen a session")
    again.add_argument(
        "--continue", action="store_const", const="", dest="resume", help="reopen the last session"
    )
    again.add_argument("--fork", metavar="ID[@TURN]", help="branch a session into a new one")
    again.add_argument("--load", type=Path, metavar="PATH", help="open a file /save wrote")
    parser.add_argument("--quiet", action="store_true", help="no status line")
    parser.add_argument("--show-thinking", action="store_true", help="show reasoning")
    parser.add_argument("--no-color", action="store_true", help="no colour (also NO_COLOR)")
    parser.add_argument("--verify", metavar="CMD", help="the check that decides done [CLI-17]")
    parser.add_argument(
        "--no-project-exec", action="store_true", help="ignore this project's tools and verify"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["prompt"]:
            return _prompt_command(argv[1:])
        if argv[:1] == ["models"]:
            return _models_command(argv[1:])
        if argv[:1] == ["memory"]:
            from edgar.cli.memory import command as memory

            return memory(argv[1:], Path.cwd())
        if argv[:1] and argv[0] in ADMIN:
            from edgar.cli.admin import command

            return command(argv, Path.cwd())
        return _run(build_parser(), argv)
    except EdgarError as exc:
        print(f"edgar: {exc}" + (f"\nhint: {exc.hint}" if exc.hint else ""), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        # The turn was cancelled and its transcript sealed before we got here.
        print("edgar: cancelled", file=sys.stderr)
        return 7


def _run(parser: argparse.ArgumentParser, argv: list[str]) -> int:
    args = parser.parse_args(argv)
    if args.fork or args.load:
        # A fork or a saved file becomes a new session here, then opens as --resume
        # would open it [CLI-22, CLI-25].
        from edgar.storage.transcript import adopt, fork

        root = (args.cwd or Path.cwd()).resolve()
        made = fork(root, args.fork) if args.fork else adopt(root, args.load.resolve())
        args.resume = made.stem
    if args.prompt is None:
        if args.json or args.events:
            parser.error("--json and --events go with -p")
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            parser.print_usage(sys.stderr)
            print("edgar: no terminal for the REPL; use -p PROMPT", file=sys.stderr)  # [CLI-4]
            return 2
        import asyncio

        from edgar.cli.repl import color_wanted, interact

        return asyncio.run(
            interact(
                cwd=args.cwd,
                model=args.model,
                mode=args.mode,
                show_thinking=args.show_thinking,
                color=color_wanted(args.no_color),
                verify=args.verify,
                project_exec=not args.no_project_exec,
                resume=args.resume,
            )
        )
    from edgar.cli.oneshot import run_prompt

    # Piped stdin is context for the prompt, never the prompt itself [CLI-3].
    attached = None if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    return run_prompt(
        args.prompt,
        cwd=args.cwd,
        model=args.model,
        mode=args.mode,
        output="json" if args.json else "events" if args.events else "text",
        quiet=args.quiet,
        show_thinking=args.show_thinking,
        attached=attached or None,
        verify=args.verify,
        project_exec=not args.no_project_exec,
        resume=args.resume,
    )


def _prompt_command(argv: list[str]) -> int:
    if argv != ["show"]:
        print("usage: edgar prompt show", file=sys.stderr)
        return 2
    from edgar.context.builder import pinned, system_text
    from edgar.context.prompts import load_prompt
    from edgar.context.tokens import approx_tokens

    prompt = load_prompt(Path.cwd())
    personality = pinned(Path.cwd(), Path.home(), [])
    sys.stdout.write(system_text(prompt.text, personality))
    tokens = approx_tokens(prompt.text)
    print(f"# {prompt.source} · ~{tokens:,} tokens of 1,500 [NFR-13]", file=sys.stderr)
    for p in personality:
        print(f"# {p.source} · ~{approx_tokens(p.text):,} tokens [CTX-19]", file=sys.stderr)
    return 0


def _models_command(argv: list[str]) -> int:
    if argv == ["list"]:
        from edgar.cli.models import list_models

        return list_models(Path.cwd())
    if argv == [] and sys.stdin.isatty():
        from edgar.cli.models import pick_command

        return pick_command(Path.cwd())
    print("usage: edgar models [list]", file=sys.stderr)
    return 2
