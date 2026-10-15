"""
The dispatcher: one entry point, one exit-code contract, one output convention.

Commands are registered rather than hard-coded into a chain of `if`s, so each
later ticket adds exactly one entry and its handler. A handler never prints and
never calls `sys.exit`; it returns an `ExitCode` and a payload, and this module
decides whether the caller sees JSON or prose. That split is what lets every
command be both an agent's tool and a person's.

`print` is unavailable here: ruff's `T20` applies to this package, and stdout is
written explicitly so a stray debugging `print` cannot masquerade as output the
contract promised.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any, Final

from factory import __version__
from factory.exit_codes import ExitCode

#: A handler takes parsed arguments and returns its code plus a payload. The
#: payload is rendered as JSON under `--json`, and as `key: value` lines otherwise.
Handler = Callable[[argparse.Namespace], tuple[ExitCode, dict[str, Any]]]

#: An argument-adder configures one subcommand's own flags.
Configure = Callable[[argparse.ArgumentParser], None]


def _no_arguments(parser: argparse.ArgumentParser) -> None:
    """Configure a subcommand that takes nothing beyond the global flags."""
    del parser


def _version(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """Report the factory's own version. The smallest command that proves wiring."""
    del args
    return ExitCode.OK, {"version": __version__}


#: name -> (help text, flag configuration, handler). The registry a new command
#: joins; nothing else in this module changes when one is added.
COMMANDS: Final[dict[str, tuple[str, Configure, Handler]]] = {
    "version": ("Print the factory's version", _no_arguments, _version),
}


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and every registered subcommand."""
    parser = argparse.ArgumentParser(
        prog="factory",
        description="Drive a ticket from intent to merge.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the result as a single JSON object instead of prose.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, (help_text, configure, _) in COMMANDS.items():
        subparser = subparsers.add_parser(name, help=help_text)
        configure(subparser)
    return parser


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    """Write a payload to stdout in whichever form the caller asked for."""
    if as_json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    for key, value in payload.items():
        sys.stdout.write(f"{key}: {value}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run one command and return its exit code.

    Returns rather than exits, so tests call it directly and `__main__` owns the
    only `sys.exit` in the package.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return int(ExitCode.MISUSE)
    _, _, handler = COMMANDS[args.command]
    code, payload = handler(args)
    _emit(payload, as_json=args.json)
    return int(code)
