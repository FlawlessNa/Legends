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

from pathlib import Path

from factory.chain import current_branch, git_dir, ticket_from_branch
from factory.hooks import governing


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
