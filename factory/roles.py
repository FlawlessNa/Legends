"""
Who does each stage, where they run, what they may write, what they may run.

`docs/factory/roles.md` states this table for people and a test keeps the two
equal. Nothing here enforces anything: the write scopes are for #163's hooks
and the command lists for #222's dispatcher. This module is the one place that
says what they are.

**Write patterns** are globs matched the way `merge.py` matches paths
(`PurePosixPath.full_match`, so `**` crosses directories). A leading `!`
excludes, and an exclusion wins wherever it stands in the list. `<n>` is the
ticket number, substituted by `scope`.

**`RADIUS`** is a marker, not a glob: it stands for `plan.md`'s radius within
`acceptance.radius`. `scope` returns it unexpanded because only the loop can
read those files; it never matches a path here.

These are the v2 roles. The v1 roles (Clerk, Specifier, QA Operator, ...) are
documented in `roles.md` for hand-worked tickets and are not modelled here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, Literal

from factory.merge import POLICY
from factory.routing import Stage

RunsIn = Literal["primary", "own-worktree", "snapshot", "worktree"]

#: Stands for plan.md's radius within acceptance.radius, for #163 to expand.
RADIUS: Final = "<radius>"

#: Allowed for every role, because the harness invokes it, not the worker.
ALWAYS_ALLOWED: Final[tuple[tuple[str, ...], ...]] = (("hook",),)


@dataclass(frozen=True)
class Role:
    """One row of the table."""

    name: str
    stages: tuple[Stage, ...]
    runs_in: RunsIn
    #: Glob patterns, with `!` to exclude, and `RADIUS` for the builder.
    writes: tuple[str, ...]
    #: Command words, after the global options: `("spec", "submit")`.
    commands: tuple[tuple[str, ...], ...]
    #: Also excludes every `merge.POLICY` hard-stop and protected pattern.
    excludes_policy: bool = False


def _ticket_files(*names: str) -> tuple[str, ...]:
    return tuple(f".factory/<n>/{name}" for name in names)


_ROLES: Final = (
    Role(
        name="designer",
        stages=(Stage.DESIGN,),
        runs_in="own-worktree",
        writes=_ticket_files("intent.md", "spec.md", "answers.md"),
        commands=(("spec", "submit"), ("park",), ("next",)),
    ),
    Role(
        name="spec-reviewer",
        stages=(Stage.SPEC_REVIEW,),
        runs_in="snapshot",
        writes=_ticket_files("spec-review.md"),
        commands=(("park",),),
    ),
    Role(
        name="planner",
        stages=(Stage.BUILD_PLANNING,),
        runs_in="snapshot",
        writes=_ticket_files("plan.md"),
        commands=(("park",), ("plan", "check")),
    ),
    Role(
        name="builder",
        stages=(Stage.BUILD_IMPLEMENTING,),
        runs_in="worktree",
        writes=(RADIUS, "tests/**", *_ticket_files("plan.md", "park.md")),
        commands=(("park",), ("next",), ("plan", "check")),
    ),
    Role(
        name="documenter",
        stages=(Stage.DOCUMENT,),
        runs_in="worktree",
        writes=(
            "docs/**",
            "**/AGENTS.md",
            "!.claude/**",
            "CONTEXT.md",
            *_ticket_files("plan.md", "park.md"),
        ),
        commands=(("doc", "check"), ("park",), ("next",)),
        excludes_policy=True,
    ),
    Role(
        name="reviewer",
        stages=(Stage.REVIEW,),
        runs_in="snapshot",
        writes=_ticket_files("review.md"),
        commands=(("park",),),
    ),
    Role(
        name="orchestrator",
        stages=(),
        runs_in="primary",
        writes=(),
        commands=(("status",), ("run",), ("feature", "new"), ("next",)),
    ),
)

#: In the order `roles.md` states them.
ROLES: Final[dict[str, Role]] = {role.name: role for role in _ROLES}

_BY_STAGE: Final[dict[Stage, Role]] = {
    stage: role for role in _ROLES for stage in role.stages
}


def role_for(stage: Stage) -> Role | None:
    """
    The worker role that runs `stage`, or None when no worker does.

    None for `accept` (the maintainer), `integrate` (the loop), `qa` (no worker
    until the QA phase), and the v1-only `plan` and `test`.
    """
    return _BY_STAGE.get(stage)


def _policy_exclusions() -> tuple[str, ...]:
    """Every hard-stop and protected pattern, read from `merge.py`, not copied."""
    return tuple(
        f"!{pattern}" for pattern in (*POLICY.hard_stop_paths, *POLICY.protected_paths)
    )


def scope(role: str, ticket: int) -> tuple[str, ...]:
    """
    The role's write patterns for `ticket`: `<n>` substituted, `RADIUS` kept.

    A role that keeps out of every merge-policy path (the Documenter) has those
    paths appended as exclusions. Raises `KeyError` for a name that is no role.
    """
    found = ROLES[role]
    patterns = tuple(pattern.replace("<n>", str(ticket)) for pattern in found.writes)
    if found.excludes_policy:
        patterns += _policy_exclusions()
    return patterns


def permits(patterns: Sequence[str], path: str) -> bool:
    """
    Whether `path` (repo-relative, forward slashes) is writable under `patterns`.

    Some positive pattern must match and no `!` pattern may. `RADIUS` is a
    marker and matches nothing here.
    """
    candidate = PurePosixPath(path)
    excluded = any(
        candidate.full_match(pattern[1:])
        for pattern in patterns
        if pattern.startswith("!")
    )
    if excluded:
        return False
    return any(
        candidate.full_match(pattern)
        for pattern in patterns
        if pattern != RADIUS and not pattern.startswith("!")
    )


def _command_words(argv: Sequence[str]) -> list[str]:
    """`argv` without the global options (`--json`) that precede the command."""
    words = list(argv)
    while words and words[0].startswith("-"):
        words.pop(0)
    return words


def allowed(role: str, argv: Sequence[str]) -> bool:
    """
    Whether `role` may run `factory <argv>`.

    An entry matches the command words that follow the global options, as a
    prefix: `spec submit` matches `["spec", "submit"]` and
    `["--json", "spec", "submit", "--x"]`. `hook` is allowed for every role.
    Raises `KeyError` for a name that is no role.
    """
    words = _command_words(argv)
    entries = (*ROLES[role].commands, *ALWAYS_ALLOWED)
    return any(words[: len(entry)] == list(entry) for entry in entries)
