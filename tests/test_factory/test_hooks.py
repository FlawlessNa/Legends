"""
The decision table, exercised without the harness.

Every case here is a branch name plus a filesystem state, which is the whole
reason the decisions are pure functions: a hook that can only be tested by
triggering Claude Code is a hook nobody will dare change later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.chain import CHAIN_DIR, current_branch, read_chain, ticket_from_branch
from factory.hooks import (
    HEARTBEAT,
    OFF_TICKET,
    decide_stop,
    decide_write,
    governing,
    session_report,
)

SPEC = "---\nticket: 7\nmethod: suite\n---\n\nbody\n"
PLAN_PROVEN = "---\nticket: 7\nproof:\n  suite: pass\n---\n\nbody\n"
PLAN_UNPROVEN = "---\nticket: 7\nproof:\n  suite: null\n---\n\nbody\n"


def _worktree(root: Path, branch: str, ticket: int) -> Path:
    """
    A directory the gate will recognise as a worktree on `branch`.

    A real `.git/HEAD`, because the gate now resolves the governing worktree
    from the path being written (#206). Before that it took a branch *string*,
    which meant these tests fed the resolution a fabricated answer and never
    exercised it.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (root / CHAIN_DIR / str(ticket)).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A worktree on ticket 7's branch, with an empty chain."""
    return _worktree(tmp_path / "wt", "issue/7-x", 7)


@pytest.fixture
def off_ticket(tmp_path: Path) -> Path:
    """A checkout on the trunk, for the cross-worktree cases."""
    root = tmp_path / "trunk"
    root.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")
    return root


def _write(repo: Path, name: str, text: str) -> None:
    (repo / ".factory" / "7" / name).write_text(text, encoding="utf-8")


# --- Which branches the hooks have an opinion about -------------------------


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("issue/7-slug", 7),
        ("issue/133-a-longer-slug", 133),
        ("issue/7", 7),
        ("movements-improvements", None),
        ("dev", None),
        ("feature/issue/7-nested", None),
        ("", None),
        (None, None),
    ],
)
def test_only_an_issue_branch_names_a_ticket(
    branch: str | None, expected: int | None
) -> None:
    assert ticket_from_branch(branch) == expected


def test_ordinary_branches_are_never_blocked(repo: Path, off_ticket: Path) -> None:
    """
    The hooks must not interfere off a ticket branch, or people disable them.

    This used to also assert the startup report was *empty*. #202 changed that
    deliberately: silence was indistinguishable from a dead hook, so the
    heartbeat now fires everywhere. Not blocking is the property that matters;
    saying nothing at all was never the point.
    """
    assert decide_write(off_ticket / "botting" / "core.py").allowed
    assert decide_stop(repo, "dev", source_changed=True).allowed
    assert session_report(repo, "dev").startswith(HEARTBEAT)


# --- The write gate ---------------------------------------------------------


def test_source_is_refused_before_a_spec_exists(repo: Path) -> None:
    decision = decide_write(repo / "botting" / "core.py")
    assert not decision.allowed
    assert "spec.md" in decision.reason


def test_source_is_refused_while_the_spec_is_unreviewed(repo: Path) -> None:
    """A spec the Builder wrote and nobody checked is not a contract."""
    _write(repo, "spec.md", SPEC)
    decision = decide_write(repo / "botting" / "core.py")
    assert not decision.allowed
    assert "spec-review.md" in decision.reason


def test_source_is_allowed_once_the_chain_is_in_order(repo: Path) -> None:
    _write(repo, "spec.md", SPEC)
    _write(repo, "spec-review.md", "---\nticket: 7\n---\n\nverdict\n")
    assert decide_write(repo / "botting" / "core.py").allowed


@pytest.mark.parametrize(
    "target", [".factory/7/spec.md", ".factory/7/intent.md", ".factory/99/intent.md"]
)
def test_the_chain_itself_is_always_writable(repo: Path, target: str) -> None:
    """
    Refusing these would forbid the only action that satisfies the gate.

    That is how a well-meaning hook becomes a deadlock, so it is tested rather
    than trusted.
    """
    assert decide_write(repo / target).allowed


@pytest.mark.parametrize(
    "target",
    [
        "factory/AGENTS.md",
        "AGENTS.md",
        "docs/factory/stages.md",
        "docs/SETUP.md",
    ],
)
def test_documentation_is_outside_the_gate(repo: Path, target: str) -> None:
    """
    The gate is scoped to source, per intent.md.

    The first implementation denied everything outside `.factory/`, which meant
    it forbade writing `factory/AGENTS.md` -- the file documenting its own
    escape hatch. Review caught it; this is the test that keeps it caught.
    """
    assert decide_write(repo / target).allowed


@pytest.mark.parametrize(
    "target", ["botting/core.py", "tests/test_x.py", "factory/cli.py"]
)
def test_source_is_still_inside_the_gate(repo: Path, target: str) -> None:
    """Narrowing the deny must not empty it."""
    assert not decide_write(repo / target).allowed


def test_the_reason_names_the_override(repo: Path) -> None:
    """A gate nobody can bypass in an emergency is a gate someone deletes."""
    decision = decide_write(repo / "botting" / "core.py")
    assert "settings.local.json" in decision.reason


# --- The stop gate ----------------------------------------------------------


def test_reading_without_changing_source_may_always_finish(repo: Path) -> None:
    """Blocking a session that only read would train everyone to switch it off."""
    assert decide_stop(repo, "issue/7-x", source_changed=False).allowed


def test_finishing_is_refused_when_source_changed_with_no_plan(repo: Path) -> None:
    decision = decide_stop(repo, "issue/7-x", source_changed=True)
    assert not decision.allowed
    assert "plan.md" in decision.reason


def test_finishing_is_refused_while_the_proof_is_unfilled(repo: Path) -> None:
    _write(repo, "plan.md", PLAN_UNPROVEN)
    decision = decide_stop(repo, "issue/7-x", source_changed=True)
    assert not decision.allowed
    assert "proof" in decision.reason


def test_finishing_is_allowed_once_the_proof_is_recorded(repo: Path) -> None:
    _write(repo, "plan.md", PLAN_PROVEN)
    assert decide_stop(repo, "issue/7-x", source_changed=True).allowed


@pytest.mark.parametrize("written", ["null", "None", ""])
def test_the_schema_s_own_word_for_not_yet_counts_as_absent(
    repo: Path, written: str
) -> None:
    _write(repo, "plan.md", f"---\nticket: 7\nproof:\n  suite: {written}\n---\n")
    assert not read_chain(repo, 7).has_proof


# --- What a session is told at startup --------------------------------------


def test_the_startup_report_names_what_is_missing(repo: Path) -> None:
    _write(repo, "intent.md", "---\nticket: 7\n---\n")
    report = session_report(repo, "issue/7-x")
    assert "ticket 7" in report
    assert "intent.md" in report
    assert "MISSING" in report
    assert "REFUSED" in report


def test_the_startup_report_stops_warning_once_the_chain_is_in_order(
    repo: Path,
) -> None:
    _write(repo, "spec.md", SPEC)
    _write(repo, "spec-review.md", "---\nticket: 7\n---\n")
    assert "REFUSED" not in session_report(repo, "issue/7-x")


# --- Worktrees, where the gates are actually supposed to run ----------------


def test_the_branch_is_found_in_a_linked_worktree(tmp_path: Path) -> None:
    """
    `factory claim` gives every ticket its own worktree, and in one `.git` is a
    *file* pointing at the real git dir -- not a directory. Reading
    `.git/HEAD` therefore found nothing, `current_branch` returned None, and
    every gate concluded "not a ticket branch" and allowed everything (#199).
    """
    real = tmp_path / "main" / ".git" / "worktrees" / "wt"
    real.mkdir(parents=True)
    (real / "HEAD").write_text("ref: refs/heads/issue/7-slug\n", encoding="utf-8")

    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")

    assert current_branch(worktree) == "issue/7-slug"


def test_an_ordinary_checkout_still_works(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/issue/9-x\n", encoding="utf-8")

    assert current_branch(tmp_path) == "issue/9-x"


def test_a_detached_head_names_no_branch(tmp_path: Path) -> None:
    """A detached HEAD holds a sha, not a ref, and names no ticket."""
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("9a8339cdeadbeef\n", encoding="utf-8")

    assert current_branch(tmp_path) is None


def test_the_heartbeat_fires_off_a_ticket_branch(repo: Path) -> None:
    """
    A proof-of-life that only appears on ticket branches is not proof.

    On the trunk the report was empty, which is indistinguishable from the
    hooks being dead -- the exact failure #199 existed to make visible, and
    which it still hid until someone merged #201 and saw nothing (#202).
    """
    report = session_report(repo, "movements-improvements")
    assert report.startswith(HEARTBEAT)


def test_the_heartbeat_does_not_narrate_at_ordinary_work(repo: Path) -> None:
    """
    Short, then silence. A chatty hook is a hook people switch off.

    Two lines now, not one: #206 made the write gate judge a file by *its*
    worktree, so a session off a ticket branch can still be refused -- for a
    ticket it was never told about. A bare deny with no startup context is the
    "I did not know" this report exists to remove.
    """
    report = session_report(repo, "dev")
    assert report.splitlines() == [HEARTBEAT, OFF_TICKET]


def test_a_ticket_branch_still_gets_the_whole_report(repo: Path) -> None:
    _write(repo, "intent.md", "---\nticket: 7\n---\n")
    report = session_report(repo, "issue/7-x")
    assert report.startswith(HEARTBEAT)
    assert "ticket 7" in report


# --- Which worktree governs a file (#206) ------------------------------------
#
# Before this, every decision came from the SESSION's branch. A session on a
# non-ticket branch made every write indifferent, including writes into a
# ticket worktree -- which is how this factory was built, and why none of its
# gates ever fired on its own construction.


def test_a_file_is_governed_by_its_own_worktree(tmp_path: Path) -> None:
    target = _worktree(tmp_path / "b", "issue/42-x", 42) / "factory" / "cli.py"
    found = governing(target)
    assert found is not None
    assert (found.ticket, found.branch) == (42, "issue/42-x")


def test_a_file_that_does_not_exist_yet_is_still_governed(repo: Path) -> None:
    """
    The normal `Write` case. Done naively -- bailing when the parent is
    missing, or resolving strictly -- every new-file write becomes indifferent,
    and the artifacts-before-code gate never fires on the first edit of a
    ticket.
    """
    found = governing(repo / "deep" / "not" / "there" / "new.py")
    assert found is not None
    assert found.ticket == 7


def test_a_path_under_no_worktree_is_not_governed(tmp_path: Path) -> None:
    """
    The factory governs this repository, not the filesystem.

    The issue body asked for an unresolvable target to fail closed. Taken
    literally that refuses every write to a scratchpad file, which is both
    noisy and none of the factory's business.
    """
    assert governing(tmp_path / "loose" / "file.py") is None


def test_a_worktree_whose_branch_cannot_be_read_has_no_ticket(tmp_path: Path) -> None:
    """
    Reachable, unlike the body's fail-closed case, and deliberately indifferent:
    a detached HEAD is a legitimate state and there is no ticket to refuse for.
    """
    root = tmp_path / "detached"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("a1b2c3d4\n", encoding="utf-8")
    found = governing(root / "factory" / "cli.py")
    assert found is not None
    assert (found.ticket, found.branch) == (None, None)


def test_a_stale_gitdir_pointer_stops_the_walk_rather_than_being_passed(
    tmp_path: Path,
) -> None:
    """
    The stop predicate is an *existing* `.git`, not a readable one.

    Stopping only where `git_dir` resolves walks straight past a worktree with
    a stale pointer and attributes its files to some ancestor checkout.
    """
    outer = _worktree(tmp_path / "outer", "issue/1-x", 1)
    inner = outer / "nested"
    inner.mkdir()
    (inner / ".git").write_text("gitdir: C:/nowhere/at/all\n", encoding="utf-8")
    found = governing(inner / "factory" / "cli.py")
    assert found is not None
    assert found.root == inner, "the walk must not reach the outer checkout"
    assert found.ticket is None


def test_resolution_never_raises(repo: Path) -> None:
    """A hook that throws blocks every edit, so the nasty inputs are enumerated."""
    for nasty in ("", "x" * 300, "with\0null", "..", "//server/share/x.py"):
        governing(Path(nasty))
        decide_write(Path(nasty), session=repo)


# --- Jurisdiction: the gate applies when EITHER side is a ticket --------------


def test_a_write_into_another_worktree_is_judged_there(tmp_path: Path) -> None:
    """
    The bug, in one test.

    Worktree A's chain is complete; worktree B's is missing `spec-review.md`.
    A session rooted in A writes source in B. Before #206 the session's branch
    decided, A's chain was consulted, and the write sailed through.
    """
    a = _worktree(tmp_path / "a", "issue/1-x", 1)
    (a / CHAIN_DIR / "1" / "spec.md").write_text(SPEC, encoding="utf-8")
    (a / CHAIN_DIR / "1" / "spec-review.md").write_text(SPEC, encoding="utf-8")

    b = _worktree(tmp_path / "b", "issue/2-x", 2)
    (b / CHAIN_DIR / "2" / "spec.md").write_text(SPEC, encoding="utf-8")

    decision = decide_write(b / "botting" / "core.py", session=a)
    assert not decision.allowed
    assert "Ticket 2" in decision.reason, "it must name B's ticket, not A's"


def test_a_ticket_session_writing_to_the_trunk_is_still_judged(
    repo: Path, off_ticket: Path
) -> None:
    """
    The row the first draft dropped while asserting it changed nothing.

    Resolving from the target alone, the trunk is on no ticket branch, so this
    write becomes allowed -- a Builder mid-ticket gaining the ability to write
    source straight into the trunk, which it cannot do today.
    """
    decision = decide_write(off_ticket / "botting" / "core.py", session=repo)
    assert not decision.allowed
    assert "Ticket 7" in decision.reason


def test_the_target_s_ticket_wins_over_the_session_s(tmp_path: Path) -> None:
    """Row 1 before row 2: the file's own worktree is the better answer."""
    a = _worktree(tmp_path / "a", "issue/1-x", 1)
    b = _worktree(tmp_path / "b", "issue/2-x", 2)
    decision = decide_write(b / "botting" / "core.py", session=a)
    assert not decision.allowed
    assert "Ticket 2" in decision.reason


def test_neither_side_a_ticket_is_indifferent(tmp_path: Path, off_ticket: Path) -> None:
    assert decide_write(off_ticket / "botting" / "core.py", session=off_ticket).allowed


def test_a_cross_worktree_chain_write_is_never_refused(tmp_path: Path) -> None:
    """
    `_always_writable` must use the GOVERNING root.

    Judged against the session's root, `relative_to` raises for another
    worktree's path, the chain write is not recognised as exempt, and the first
    thing the new gate refuses is the artifact write that would satisfy it --
    the #189 deadlock, back through a side door.
    """
    a = _worktree(tmp_path / "a", "issue/1-x", 1)
    b = _worktree(tmp_path / "b", "issue/2-x", 2)
    for exempt in (
        b / CHAIN_DIR / "2" / "intent.md",
        b / "docs" / "factory" / "stages.md",
        b / "AGENTS.md",
    ):
        assert decide_write(exempt, session=a).allowed, exempt
