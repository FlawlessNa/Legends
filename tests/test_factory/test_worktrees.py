"""Finding the worktree a ticket's artifact chain lives in (#217)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from factory.worktrees import ticket_worktrees, worktree_for

from .test_hooks import _linked, _primary


def test_a_ticket_s_worktree_is_found_from_the_primary_checkout(
    tmp_path: Path,
) -> None:
    main = _primary(tmp_path / "main", "dev")
    own = _linked(main, tmp_path / "wt7", "issue/7-x", 7)
    _linked(main, tmp_path / "wt8", "issue/8-x", 8)
    assert worktree_for(main, 7) == (own,)


def test_a_subdirectory_resolves_to_its_worktree_root(tmp_path: Path) -> None:
    main = _primary(tmp_path / "main", "dev")
    own = _linked(main, tmp_path / "wt7", "issue/7-x", 7)
    (main / "botting").mkdir()
    assert worktree_for(main / "botting", 7) == (own,)


def test_no_worktree_for_the_ticket_is_an_empty_answer(tmp_path: Path) -> None:
    main = _primary(tmp_path / "main", "dev")
    _linked(main, tmp_path / "wt8", "issue/8-x", 8)
    assert worktree_for(main, 7) == ()


def test_two_worktrees_for_one_ticket_are_both_returned(tmp_path: Path) -> None:
    main = _primary(tmp_path / "main", "dev")
    first = _linked(main, tmp_path / "wt-a", "issue/7-a", 7)
    second = _linked(main, tmp_path / "wt-b", "issue/7-b", 7)
    assert set(worktree_for(main, 7)) == {first, second}


@pytest.mark.parametrize("subdirectory", [False, True])
def test_the_primary_on_the_ticket_branch_is_found_once(
    tmp_path: Path, subdirectory: bool
) -> None:
    """
    The session is the primary checkout and is on the ticket branch, so it is
    both "the session's own root" and "the primary". Counted twice it would
    trip the ambiguity exit for a ticket with one worktree.
    """
    main = _primary(tmp_path / "main", "issue/7-x")
    (main / ".factory" / "7").mkdir(parents=True)
    (main / "botting").mkdir()
    start = main / "botting" if subdirectory else main
    assert worktree_for(start, 7) == (main,)


def test_the_primary_on_the_ticket_branch_is_found_from_a_linked_session(
    tmp_path: Path,
) -> None:
    main = _primary(tmp_path / "main", "issue/7-x")
    other = _linked(main, tmp_path / "wt8", "issue/8-x", 8)
    assert worktree_for(other, 7) == (main,)


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive paths")
def test_the_same_directory_spelled_with_another_case_is_one_worktree(
    tmp_path: Path,
) -> None:
    main = _primary(tmp_path / "main", "issue/7-x")
    shouting = Path(str(main).upper())
    assert len(worktree_for(shouting, 7)) == 1


def test_ticket_worktrees_is_the_same_function_the_cli_exports() -> None:
    from factory import cli

    assert cli.ticket_worktrees is ticket_worktrees


def test_a_primary_checkout_in_a_folder_named_worktrees_is_its_own_repository(
    tmp_path: Path,
) -> None:
    """
    One helper answers "which repository", and shape decides, not the name.

    The old heuristic read `.git`'s parent being called `worktrees` as "this is
    a linked worktree", so a primary checkout in a folder of that name got its
    grandparent as the repository (review of #207).
    """
    from factory import worktrees
    from factory.hooks import _common

    root = _primary(tmp_path / "worktrees", "dev")
    assert _common(root) == root / ".git"
    assert worktrees.common_dir(root) == root / ".git"


def test_a_linked_worktree_and_its_primary_share_one_repository(
    tmp_path: Path,
) -> None:
    from factory.hooks import _common

    main = _primary(tmp_path / "main", "dev")
    own = _linked(main, tmp_path / "wt7", "issue/7-x", 7)
    assert _common(own) == _common(main) == main / ".git"
