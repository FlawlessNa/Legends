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
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from factory import __version__
from factory.chain import (
    CHAIN_DIR,
    Chain,
    UnknownChainVersion,
    current_branch,
    read_chain,
    ticket_from_branch,
)
from factory.exit_codes import ExitCode
from factory.hooks import (
    INDIFFERENT,
    Decision,
    decide_stop,
    decide_write,
    governing,
    session_report,
)
from factory.merge import check as check_merge
from factory.models import TABLE_PATH, TableError
from factory.models import load as load_models
from factory.models import resolve as resolve_model
from factory.routing import MalformedVerdict, Stage, resolve
from factory.state import StateError, TicketState
from factory.state import load as load_state
from factory.worktrees import (
    log_write,
    logged_worktrees,
    worktree_for,
)
from factory.worktrees import ticket_worktrees as ticket_worktrees  # noqa: PLC0414

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


def _session_checkout() -> Path:
    """The worktree root the process runs in; a subdirectory resolves to it."""
    found = governing(Path.cwd())
    return found.root if found is not None else Path.cwd()


def _ticket_root(session: Path, ticket: int) -> Path | tuple[ExitCode, dict[str, Any]]:
    """
    The one worktree holding ticket `ticket`'s chain, or the refusal to give.

    A chain is committed on its ticket's branch, so it exists only in the
    worktree with that branch checked out -- not in the session's, unless the
    session happens to be there. None is misuse (the caller named a ticket
    nobody is working); several is a person's to settle, because picking one
    would route the ticket by accident (#217).
    """
    found = worktree_for(session, ticket)
    if len(found) == 1:
        return found[0]
    if not found:
        return ExitCode.MISUSE, {
            "error": f"no worktree is on a branch named issue/{ticket}-*. "
            "Start the ticket first, or run this from its worktree."
        }
    return ExitCode.NEEDS_HUMAN, {
        "error": f"{len(found)} worktrees are on issue/{ticket}-*: "
        + ", ".join(str(root) for root in found)
        + ". Remove all but one."
    }


def _next(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """
    Which stage this ticket is in, and what to do about it.

    The answer is computed from the artifact chain, never judged, so two callers
    on the same chain get the same one. An agent's first action on any ticket is
    this command; it does not choose a stage for itself.
    """
    session = _session_checkout()
    repo_root = session
    if args.ticket:
        located = _ticket_root(session, args.ticket)
        if isinstance(located, tuple):
            return located
        repo_root = located
    branch = f"issue/{args.ticket}-" if args.ticket else current_branch(session)
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


def _configure_model(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "ticket", nargs="?", type=int, help="Ticket number; defaults to the branch's."
    )
    parser.add_argument(
        "--stage",
        help="Ask about this stage directly instead of computing it from the chain.",
    )


def _model(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """
    Which model runs this stage, and why.

    The agent never chooses: one asked to choose picks the strong model every
    time. Argument errors are MISUSE and table errors are NEEDS_HUMAN, because
    "you asked wrongly" and "the maintainer's file is wrong" have nothing in
    common but their unhappiness.
    """
    #: The table is the **session's**, never the ticket's: a ticket branch must
    #: not be able to change its own model routing (the principle of #216).
    session = _session_checkout()
    chain_root = session
    chain: Chain | None = None
    ticket: int | None = args.ticket
    if ticket is not None:
        located = _ticket_root(session, ticket)
        if isinstance(located, tuple):
            return located
        chain_root = located

    if args.stage:
        try:
            stage = Stage(args.stage)
        except ValueError:
            return ExitCode.MISUSE, {
                "error": f"{args.stage!r} is not a stage. The stages are "
                f"{[str(member) for member in Stage]}."
            }
        if ticket is not None:
            chain = read_chain(chain_root, ticket)
    else:
        branch = f"issue/{ticket}-" if ticket else current_branch(session)
        try:
            step = resolve(chain_root, branch)
        except MalformedVerdict as bad:
            return ExitCode.NEEDS_HUMAN, {"error": str(bad)}
        if step.blocked:
            return ExitCode.NEEDS_HUMAN, {
                "ticket": step.ticket,
                "blocked_by": step.blocked_by,
                "error": "the chain says stop; no stage to route a model for",
            }
        if step.stage is None:
            return ExitCode.MISUSE, {
                "error": "no ticket on this branch. Pass a ticket or --stage."
            }
        stage, ticket = step.stage, step.ticket
        chain = read_chain(chain_root, ticket) if ticket else None

    #: Escalation reads the loop's state, and only a v2 chain has any. A v1
    #: chain, and a bare `--stage`, pass none, so neither can ever escalate.
    loop_state: TicketState | None = None
    if chain is not None:
        try:
            if chain.version == 2:
                loop_state = load_state(chain_root, chain.ticket)
        except (UnknownChainVersion, StateError) as unreadable:
            return ExitCode.NEEDS_HUMAN, {"error": str(unreadable)}

    try:
        table = load_models(session / TABLE_PATH)
    except TableError as broken:
        return ExitCode.NEEDS_HUMAN, {"error": str(broken), "table": str(TABLE_PATH)}

    choice = resolve_model(table, stage, chain, loop_state)
    return ExitCode.OK, {
        "ticket": ticket,
        "stage": str(stage),
        "model": choice.model,
        "tier": choice.tier,
        "rule": choice.rule,
        "record": choice.record,
    }


#: The two kinds of park (artifacts.md): a person must act, or the spec has a gap.
PARK_KINDS: Final = {"reason": "needs-human", "question": "spec-gap"}


def _configure_park(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "ticket", nargs="?", type=int, help="Ticket number; defaults to the branch's."
    )
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--reason", help="Why a person must take over (needs-human).")
    kind.add_argument("--question", help="A gap in the spec (spec-gap).")


def _park(args: argparse.Namespace) -> tuple[ExitCode, dict[str, Any]]:
    """
    Hand the ticket back: write `park.md` in the ticket's own worktree.

    Writes nothing else, and never `state.json`: the loop reads the park and
    records it. The stage is whatever routing says at this moment, and null when
    it names none or cannot say -- a worker parking because the chain is broken
    must still get its park written.
    """
    which = "reason" if args.reason is not None else "question"
    text = str(getattr(args, which)).strip()
    if not text:
        return ExitCode.MISUSE, {"error": f"--{which} must not be empty."}

    session = _session_checkout()
    root = session
    ticket: int | None = args.ticket
    if ticket is not None:
        located = _ticket_root(session, ticket)
        if isinstance(located, tuple):
            return located
        root = located
    else:
        ticket = ticket_from_branch(current_branch(session))
        if ticket is None:
            return ExitCode.MISUSE, {
                "error": "no ticket on this branch. Pass a ticket number."
            }

    target = root / CHAIN_DIR / str(ticket) / "park.md"
    kind = PARK_KINDS[which]
    stage: str | None
    try:
        step = resolve(root, f"issue/{ticket}-")
        stage = str(step.stage) if step.stage else None
    except ValueError:
        stage = None

    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    front = [
        "---",
        f"ticket: {ticket}",
        f"kind: {kind}",
        f"stage: {stage or 'null'}",
        f"parked_at: {stamp}",
        "---",
    ]
    body = "\n".join([*front, "", text, ""])
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    except FileExistsError:
        recorded = read_chain(root, ticket).park.get("kind", "unknown")
        return ExitCode.NEEDS_HUMAN, {
            "error": f"{target} already exists (kind: {recorded}). "
            "A person or the loop decides what an existing park means."
        }
    return ExitCode.OK, {
        "ticket": ticket,
        "kind": kind,
        "stage": stage,
        "path": str(target),
    }


#: name -> (help text, flag configuration, handler). The registry a new command
#: joins; nothing else in this module changes when one is added.
COMMANDS: Final[dict[str, tuple[str, Configure, Handler]]] = {
    "version": ("Print the factory's version", _no_arguments, _version),
    "next": (
        "Which stage a ticket is in, and what to do next",
        _configure_next,
        _next,
    ),
    "model": (
        "Which model runs a stage of a ticket, and why",
        _configure_model,
        _model,
    ),
    "merge": ("Evaluate the auto-merge policy for a PR", _configure_merge, _merge),
    "park": (
        "Hand a ticket back to a person: write park.md",
        _configure_park,
        _park,
    ),
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

#: Said at session start when no base resolves for the worktree. A Stop that
#: allows prints nothing, so this is the only place the gap can be reported.
NO_BASE: Final = (
    "The committed range is not checked: no base commit resolves for this "
    "worktree (no .factory/<n>/ commit with a parent, and no origin/HEAD), so "
    "Stop judges uncommitted changes alone. To fix origin/HEAD, run: "
    "git remote set-head origin --auto"
)


def _hooks_disabled() -> bool:
    """The documented per-machine override, set in settings.local.json."""
    return os.environ.get("FACTORY_HOOKS", "").strip().lower() == "off"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """One git command in `root`; None when git cannot be run at all."""
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None


def _rev(root: Path, *args: str) -> str | None:
    """A single commit id git prints for `args`, or None when it prints none."""
    done = _git(root, *args)
    if done is None or done.returncode != 0:
        return None
    lines = done.stdout.split()
    return lines[0] if lines else None


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    done = _git(root, "merge-base", "--is-ancestor", older, newer)
    return done is not None and done.returncode == 0


def _base(root: Path) -> str | None:
    """
    The commit this worktree's ticket started from, or None when none resolves.

    **The ticket's own starting point, not a ref.** It is the parent of the
    oldest commit on HEAD's history that touches the ticket's `.factory/<n>/`:
    the intent-and-spec commit the process puts first. A ref cannot be it --
    the default branch moves, a push adds refs, a child branch is cut from a
    parent's tip -- and a merge-base against any of those would count another
    ticket's source as this one's.

    Two things can make that parent too old, and in both the merge-base of HEAD
    and `origin/HEAD` is later, so the later of the two wins whenever one is an
    ancestor of the other: the default branch merged into the ticket (its own
    files would otherwise count), and a chain that already sits on the default
    branch (a reopened ticket, or intent committed before branching).

    A chain commit with no parent, or no chain commit at all, takes the
    merge-base alone; with that missing too the answer is None, and the change
    set is the uncommitted paths alone.
    """
    ticket = ticket_from_branch(current_branch(root))
    if ticket is None:
        return None
    first = _rev(
        root, "log", "--reverse", "--format=%H", "--", f"{CHAIN_DIR}/{ticket}/"
    )
    parent = _rev(root, "rev-parse", "--verify", "-q", f"{first}^") if first else None
    default = _rev(root, "merge-base", "HEAD", "origin/HEAD")
    if parent is None or default is None:
        return parent or default
    if _is_ancestor(root, parent, default):
        return default
    return parent


def _changed_paths(root: Path) -> set[str]:
    """
    Every path outside `.factory/` the ticket changed: committed since its base,
    plus whatever the working tree holds.

    Committed source was invisible when only `git status` was read, so
    committing before stopping escaped the proof gate. A git failure leaves the
    set empty, as it always did.
    """
    paths: set[str] = set()
    base = _base(root)
    if base is not None:
        done = _git(root, "diff", "--name-only", f"{base}...HEAD")
        if done is not None and done.returncode == 0:
            paths.update(line.strip() for line in done.stdout.splitlines())
    status = _git(root, "status", "--porcelain")
    if status is not None:
        for line in status.stdout.splitlines():
            #: A rename reads `old -> new`; the new path is the one that exists.
            paths.add(line[3:].rpartition(" -> ")[2].strip().strip('"'))
    prefix = f"{CHAIN_DIR}/"
    return {path for path in paths if path and not path.startswith(prefix)}


def _source_changed(root: Path) -> bool:
    """
    Whether the ticket changed anything outside the artifact chain.

    Shells out to git, which `decide_write` deliberately does not: `Stop` fires
    once per turn, so a few processes are affordable where one per edit is not.
    """
    return bool(_changed_paths(root))


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

    raw = _read_stdin()
    repo_root = _session_root(raw)
    branch = current_branch(repo_root)
    payload: dict[str, Any] = {}

    if args.event == "session-start":
        report = session_report(repo_root, branch)
        if report and ticket_from_branch(branch) and _base(repo_root) is None:
            report += "\n\n" + NO_BASE
        if report:
            payload = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": report,
                }
            }
    elif args.event == "pre-tool-use":
        target = _written_path(raw)
        if target is not None:
            decision = decide_write(target, session=repo_root)
            if decision.allowed:
                #: After the decision, and unable to change it: an error here
                #: is swallowed, because a broken log must not fail a write
                #: open or closed.
                with contextlib.suppress(Exception):
                    log_write(repo_root, target, raw.get("session_id"))
            else:
                payload = {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "permissionDecision": "deny",
                        "permissionDecisionReason": decision.reason,
                    }
                }
    else:
        decision = _stop_everywhere(repo_root, raw.get("session_id"))
        if not decision.allowed:
            payload = {"decision": "block", "reason": decision.reason}

    if payload:
        sys.stdout.write(json.dumps(payload))
    return int(ExitCode.OK)


def _read_stdin() -> dict[str, Any]:
    """
    The harness event, or an empty mapping when there is nothing to read.

    **A terminal is nothing to read.** Every event reads its JSON, so a person
    running `factory-hook.sh session-start` by hand -- which is how SKILL.md
    says to check the gates are alive -- would otherwise wait forever on input
    nobody is going to type.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        text = sys.stdin.read()
    except OSError, ValueError:
        return {}
    try:
        loaded = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _session_root(event: dict[str, Any]) -> Path:
    """
    The session's directory: the event's `cwd` when it names one, else ours.

    The event is the harness's own statement of where the session is. The
    process cwd is where the hook happened to be started, which is the same
    place today but is not promised -- a launcher may run hooks from anywhere
    (#216). A `cwd` naming no existing directory is ignored rather than
    trusted, so a stale event cannot move the session somewhere imaginary.

    **The worktree root, not the directory as given.** The session may sit in a
    subdirectory, and everything downstream -- `current_branch`,
    `ticket_worktrees`, `session_report` -- expects a root. Taken raw, a `cwd`
    of `<worktree>/botting` read as "no ticket" and silenced the Stop gate.
    """
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd and Path(cwd).is_dir():
        found = governing(Path(cwd))
        return found.root if found is not None else Path(cwd)
    return Path.cwd()


def _written_path(event: dict[str, Any]) -> Path | None:
    """
    The absolute path a tool call would write, or None when it writes nothing.

    **Anchored before it is returned.** The tool input may carry a relative
    path -- `PreToolUse` fires on the model's raw arguments, before the tool
    validates them -- and a relative path resolved later lands against the
    hook's own cwd, which is the session's worktree and not the target's. The
    gate would then walk up to the session's `.git` and answer about the wrong
    ticket, which is the very bug #206 fixes, surviving its own fix.

    The harness event carries its own `cwd`; use it when present, since it is
    what the model's relative path was written against. Otherwise the process
    cwd, which is the best guess available.
    """
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in _PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return _anchored(Path(value), event.get("cwd"))
    return None


def _anchored(target: Path, event_cwd: object) -> Path:
    """An absolute target, anchored on the event's cwd when it needs one."""
    if target.is_absolute():
        return target
    base = Path(event_cwd) if isinstance(event_cwd, str) and event_cwd else Path.cwd()
    return base / target


def _stop_everywhere(repo_root: Path, session_id: object = None) -> Decision:
    """
    The proof gate, over the session's own worktree and every one it wrote.

    Judged against the session's worktree alone, this gate was **dead** in the
    workflow the factory was built under: the session sits in the main checkout
    on a non-ticket branch, so `decide_stop` returned indifference on every turn
    forever (#206). Judged over *every* ticket worktree it blocked a session for
    another ticket's unfinished work (#207). The scope is now the session's own
    worktree, when it is on a ticket branch, plus each worktree in its write log
    (`pre-tool-use` records them); unrelated worktrees are never judged.

    The first refusal wins; fixing it reveals the next. Every refusal names the
    worktree, the ticket and the base it judged against, so a surprise can be
    traced to the commit range behind it.
    """
    scope: dict[Path, Path] = {}
    if ticket_from_branch(current_branch(repo_root)) is not None:
        scope[repo_root.resolve()] = repo_root
    logged: tuple[Path, ...] = ()
    with contextlib.suppress(Exception):
        logged = logged_worktrees(repo_root, session_id)
    for root in logged:
        scope.setdefault(root.resolve(), root)

    for root in scope.values():
        branch = current_branch(root)
        decision = decide_stop(root, branch, _source_changed(root))
        if not decision.allowed:
            base = _base(root) or "none (no base resolves; uncommitted changes only)"
            return Decision(
                allowed=False,
                reason=(
                    f"{decision.reason}\n"
                    f"Judged: worktree {root}, ticket {ticket_from_branch(branch)}, "
                    f"base {base}."
                ),
            )
    return INDIFFERENT
