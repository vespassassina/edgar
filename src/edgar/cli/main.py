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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar",
        description="The agent harness you can read in an afternoon.",
        epilog="Other commands: edgar prompt show, edgar models list",
    )
    parser.add_argument("--version", action="version", version=f"edgar {__version__}")
    parser.add_argument("-p", "--prompt", help="run one turn non-interactively and exit")
    parser.add_argument("--model", help="provider/model, for example fake/test")
    parser.add_argument("--mode", choices=get_args(Mode), help="permission mode; required with -p")
    parser.add_argument("--cwd", type=Path, help="working directory (default: here)")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["prompt"]:
            return _prompt_command(argv[1:])
        if argv[:1] == ["models"]:
            return _models_command(argv[1:])
        return _run(build_parser(), argv)
    except EdgarError as exc:
        print(f"edgar: {exc}", file=sys.stderr)
        if exc.hint:
            print(f"hint: {exc.hint}", file=sys.stderr)
        return exc.exit_code


def _run(parser: argparse.ArgumentParser, argv: list[str]) -> int:
    args = parser.parse_args(argv)
    if args.prompt is None:
        # The REPL arrives in M4. Until then, saying so with a usage exit code beats
        # pretending to work.
        parser.print_usage(sys.stderr)
        print("edgar: the interactive REPL arrives in M4; use -p for now", file=sys.stderr)
        return 2
    from edgar.cli.oneshot import run_prompt

    return run_prompt(args.prompt, cwd=args.cwd, model=args.model, mode=args.mode)


def _prompt_command(argv: list[str]) -> int:
    if argv != ["show"]:
        print("usage: edgar prompt show", file=sys.stderr)
        return 2
    from edgar.context.prompts import load_prompt
    from edgar.context.tokens import approx_tokens

    prompt = load_prompt(Path.cwd())
    sys.stdout.write(prompt.text)
    tokens = approx_tokens(prompt.text)
    print(f"# {prompt.source} · ~{tokens:,} tokens of 1,500 [NFR-13]", file=sys.stderr)
    return 0


def _models_command(argv: list[str]) -> int:
    if argv != ["list"]:
        print("usage: edgar models list", file=sys.stderr)
        return 2
    from edgar.cli.models import list_models

    return list_models(Path.cwd())
