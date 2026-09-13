from __future__ import annotations

import argparse
import sys

from edgar import __version__

# Nothing heavy may be imported at module level here: this module is on the path of
# every run, and tests/e2e/test_startup.py fails the build if httpx, rich,
# prompt_toolkit, jsonschema, yaml, keyring or any edgar.providers module is pulled
# in (NFR-1, ADR-0012).


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar",
        description="The agent harness you can read in an afternoon.",
    )
    parser.add_argument("--version", action="version", version=f"edgar {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    # The REPL arrives in M4 and -p in M1. Until then there is nothing to run, and
    # saying so on stderr with a usage exit code beats pretending to work.
    parser.print_usage(sys.stderr)
    print("edgar: nothing to run yet; only --version is implemented (M0)", file=sys.stderr)
    return 2
