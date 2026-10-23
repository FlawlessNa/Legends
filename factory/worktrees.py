"""
Which worktrees a repository has, and which of them a ticket lives in.

A ticket's artifact chain is committed on its own branch, so it exists only in
the worktree that has that branch checked out. A session in the primary checkout
(or in another ticket's worktree) is not looking at it, which is why `factory
next <n>` cannot read the chain from the current directory (#217).

Nothing here runs git: every answer is read from `.git` by hand, as
`current_branch` does, because the hooks call this on every turn.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Final

from factory.chain import CHAIN_DIR, current_branch, git_dir, ticket_from_branch
from factory.hooks import governing

#: A session id the log will use as a directory name. Anything else -- a path
#: separator, a dot, an empty string, a number -- writes no log at all, so an id
#: can never name somewhere outside `<common>/factory/sessions/`.
SESSION_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def ticket_worktrees(repo_root: Path) -> tuple[Path, ...]:
    """
    Every worktree of this repository that is on a ticket branch.

    Read from `<common>/worktrees/*/gitdir`, not from `git worktree list`: the
    same no-subprocess habit as `current_branch`, and this is a directory
    listing. The session's own root is included when it qualifies, so a session
    working inside its own ticket worktree is judged exactly as before.
    """
    found: list[Path] = []
    here = git_dir(repo_root)
    if here is None:
        return ()
    if ticket_from_branch(current_branch(repo_root)) is not None:
        found.append(repo_root)

    #: In a linked worktree this is `<main>/.git/worktrees/<name>`; the shared
    #: directory is its grandparent, and `commondir` names it when it is not.
    common = here.parent.parent if here.parent.name == "worktrees" else here
    try:
        entries = sorted((common / "worktrees").iterdir())
    except OSError:
        return tuple(found)

    for entry in entries:
        try:
            root = Path((entry / "gitdir").read_text(encoding="utf-8").strip()).parent
        except OSError:
            continue
        if root in found or not root.is_dir():
            continue
        if ticket_from_branch(current_branch(root)) is not None:
            found.append(root)
    return tuple(found)


def worktree_for(repo_root: Path, ticket: int) -> tuple[Path, ...]:
    """
    Every worktree of this repository on an `issue/<ticket>-*` branch.

    `repo_root` may be a subdirectory; it is resolved to its worktree root
    first. The candidates are `ticket_worktrees` plus the primary checkout, the
    one worktree it cannot list because it is not under `<common>/worktrees`.

    **Deduplicated by `Path` equality, not by string.** The primary checkout is
    reached twice when it is the session and is on the ticket branch, and the
    two spellings can differ in case on Windows. Counted twice it would read as
    two worktrees for one ticket, and the caller would stop on an ambiguity
    that does not exist.

    Empty means no worktree; more than one means the caller must not choose.
    """
    found = governing(repo_root)
    root = found.root if found is not None else repo_root
    here = git_dir(root)
    if here is None:
        return ()

    common = here.parent.parent if here.parent.name == "worktrees" else here
    candidates = [*ticket_worktrees(root), common.parent]

    unique: dict[Path, Path] = {}
    for candidate in candidates:
        if ticket_from_branch(current_branch(candidate)) != ticket:
            continue
        unique.setdefault(candidate.resolve(), candidate)
    return tuple(unique.values())


# --- What a session wrote (#207) ---------------------------------------------
#
# Stop judges the session's own worktree and every ticket worktree it wrote.
# The write log is how Stop learns the second set: `pre-tool-use` records a
# worktree after an allowed write, and `stop` reads the records back.
#
# One file per (session, worktree), named by a hash of the worktree, so two
# hooks running at once create different files and neither can lose the other's
# entry. A shared file appended to by concurrent hooks lost 26-27% of its lines
# when the spec review measured it.


def common_dir(root: Path) -> Path | None:
    """The repository's shared git directory, or None when `root` is in none."""
    here = git_dir(root)
    if here is None:
        return None
    return here.parent.parent if here.parent.name == "worktrees" else here


def _session_dir(common: Path, session_id: str) -> Path:
    return common / "factory" / "sessions" / session_id


def _valid(session_id: object) -> str | None:
    if isinstance(session_id, str) and SESSION_ID.fullmatch(session_id):
        return session_id
    return None


def log_write(session: Path, target: Path, session_id: object) -> None:
    """
    Record the ticket worktree `target` lives in, for this session.

    Call it only after the write was allowed. It records nothing unless the
    target is outside `.factory/`, lies in a worktree on a ticket branch, and is
    in the same repository as the session (`decide_write`'s identity rule). The
    session's own worktree is recorded too; it is judged anyway, and a session
    that later leaves it should still be accountable.

    **It may raise.** The caller owns the `try/except`: the log is never allowed
    to change a decision, and swallowing here would hide the failure from the
    one place that must decide to ignore it.
    """
    valid = _valid(session_id)
    if valid is None:
        return
    found = governing(target)
    if found is None or found.ticket is None:
        return
    common = common_dir(found.root)
    if common is None or common != common_dir(session):
        return
    try:
        relative = target.resolve().relative_to(found.root.resolve())
    except ValueError, OSError:
        return
    if relative.parts[:1] == (CHAIN_DIR,):
        return

    root = found.root.resolve()
    name = hashlib.sha1(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
    directory = _session_dir(common, valid)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(str(root), encoding="utf-8")


def logged_worktrees(session: Path, session_id: object) -> tuple[Path, ...]:
    """
    The ticket worktrees this session wrote that still exist.

    Deduplicated by resolved `Path`, so a case difference on Windows cannot
    count one worktree twice. A missing worktree, or one no longer on a ticket
    branch, is skipped rather than reported.
    """
    valid = _valid(session_id)
    common = common_dir(session)
    if valid is None or common is None:
        return ()
    try:
        entries = sorted(_session_dir(common, valid).iterdir())
    except OSError:
        return ()
    unique: dict[Path, Path] = {}
    for entry in entries:
        try:
            root = Path(entry.read_text(encoding="utf-8").strip())
        except OSError:
            continue
        if not root.is_dir() or ticket_from_branch(current_branch(root)) is None:
            continue
        unique.setdefault(root.resolve(), root)
    return tuple(unique.values())
