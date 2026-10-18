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
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from factory import __version__
from factory.chain import current_branch
from factory.exit_codes import ExitCode
from factory.hooks import (
    decide_stop,
    decide_write,
    session_report,
)
from factory.merge import check as check_merge
from factory.routing import MalformedVerdict, resolve

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


def _pull_request_number(text: str) -> int:
    """A PR number, refused at parse time so a typo is misuse, not a verdict."""
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"not a pull request number: {text!r}")
    return int(text)


def _configure_merge(parser: argparse.ArgumentParser) -> None:
    """`merge check <pr>`, nested so `merge` gains actions without new commands."""
    actions = parser.add_subparsers(dest="merge_action", metavar="ACTION")
    check = actions.add_parser(
        "check", help="Evaluate the auto-merge policy, exactly as CI does"
    )
    check.add_argument("pr", type=_pull_request_number, help="The PR number.")


def _merge(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """Evaluate docs/factory/merge-policy.md for one PR. Never merges."""
    if args.merge_action != "check":
        return ExitCode.MISUSE, {"error": "usage: factory merge check <pr>"}
    return check_merge(args.pr)


def _configure_next(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "ticket", nargs="?", type=int, help="Ticket number; defaults to the branch's."
    )


def _next(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """
    Which stage this ticket is in, and what to do about it.

    The answer is computed from the artifact chain, never judged, so two callers
    on the same chain get the same one. An agent's first action on any ticket is
    this command; it does not choose a stage for itself.
    """
    repo_root = Path.cwd()
    branch = f"issue/{args.ticket}-" if args.ticket else current_branch(repo_root)
    try:
        step = resolve(repo_root, branch)
    except MalformedVerdict as bad:
        return ExitCode.NEEDS_HUMAN, {"error": str(bad)}

    payload: dict[str, Any] = {
        "ticket": step.ticket,
        "stage": str(step.stage) if step.stage else None,
        "role": step.role,
        "section": step.section,
        "do": list(step.do),
        "blocked_by": step.blocked_by,
        "artifact_missing": step.artifact_missing,
    }
    if step.note:
        payload["note"] = step.note
    return (ExitCode.NEEDS_HUMAN if step.blocked else ExitCode.OK), payload


#: name -> (help text, flag configuration, handler). The registry a new command
#: joins; nothing else in this module changes when one is added.
COMMANDS: Final[dict[str, tuple[str, Configure, Handler]]] = {
    "version": ("Print the factory's version", _no_arguments, _version),
    "next": (
        "Which stage a ticket is in, and what to do next",
        _configure_next,
        _next,
    ),
    "merge": ("Evaluate the auto-merge policy for a PR", _configure_merge, _merge),
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
    for name, (help_text, configure) in RAW_COMMANDS.items():
        configure(subparsers.add_parser(name, help=help_text))
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
    if args.command in RAW_COMMANDS:
        return _run_hook(args)
    _, _, handler = COMMANDS[args.command]
    code, payload = handler(args)
    _emit(payload, as_json=args.json)
    return int(code)


# --- The hook subcommand -----------------------------------------------------
#
# The one deliberate exception to everything above. A hook speaks the harness's
# JSON protocol on stdin and stdout, not the factory's payload-and-exit-code
# contract, so it bypasses `_emit` and always exits 0: a hook that fails must
# not take the session down with it.

#: Harness events this can answer, mapped to their `hookEventName`.
HOOK_EVENTS: Final[dict[str, str]] = {
    "session-start": "SessionStart",
    "pre-tool-use": "PreToolUse",
    "stop": "Stop",
}

#: Tool inputs that name a path to be written.
_PATH_KEYS: Final = ("file_path", "notebook_path")


def _hooks_disabled() -> bool:
    """The documented per-machine override, set in settings.local.json."""
    return os.environ.get("FACTORY_HOOKS", "").strip().lower() == "off"


def _source_changed(repo_root: Path) -> bool:
    """
    Whether the working tree holds a change outside the artifact chain.

    Shells out to git, which `decide_write` deliberately does not: `Stop` fires
    once per turn, so one process is affordable where one per edit is not.
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return False
    for line in out.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if path and not path.startswith(".factory/"):
            return True
    return False


def _configure_hook(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("event", choices=sorted(HOOK_EVENTS), help="The harness event.")


#: Subcommands that speak a foreign protocol and bypass `_emit` entirely.
#: Declared here rather than beside COMMANDS because its handler is defined in
#: this section, and a forward reference would only be resolvable at call time.
RAW_COMMANDS: Final[dict[str, tuple[str, Configure]]] = {
    "hook": ("Answer a Claude Code hook event (reads JSON on stdin)", _configure_hook),
}


def _run_hook(args: argparse.Namespace) -> int:
    """Answer one harness event. Always exits 0; the verdict is in the JSON."""
    event = HOOK_EVENTS[args.event]
    if _hooks_disabled():
        return int(ExitCode.OK)

    repo_root = Path.cwd()
    branch = current_branch(repo_root)
    payload: dict[str, Any] = {}

    if args.event == "session-start":
        report = session_report(repo_root, branch)
        if report:
            payload = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": report,
                }
            }
    elif args.event == "pre-tool-use":
        raw = _read_stdin()
        target = _written_path(raw)
        if target is not None:
            decision = decide_write(repo_root, branch, target)
            if not decision.allowed:
                payload = {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "permissionDecision": "deny",
                        "permissionDecisionReason": decision.reason,
                    }
                }
    else:
        decision = decide_stop(repo_root, branch, _source_changed(repo_root))
        if not decision.allowed:
            payload = {"decision": "block", "reason": decision.reason}

    if payload:
        sys.stdout.write(json.dumps(payload))
    return int(ExitCode.OK)


def _read_stdin() -> dict[str, Any]:
    """The harness event, or an empty mapping when there is nothing to read."""
    try:
        text = sys.stdin.read()
    except OSError, ValueError:
        return {}
    try:
        loaded = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _written_path(event: dict[str, Any]) -> Path | None:
    """The path a tool call would write, or None when it writes nothing."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    return None
