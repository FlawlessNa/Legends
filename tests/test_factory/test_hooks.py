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
    IN_PRIMARY,
    OFF_TICKET,
    _common,
    _is_primary,
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


def _primary(root: Path, branch: str) -> Path:
    """A primary checkout: `.git` is a DIRECTORY."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    return root


def _linked(primary: Path, root: Path, branch: str, ticket: int | None = None) -> Path:
    """
    A genuine linked worktree of `primary`: `.git` is a FILE holding a pointer.

    No existing fixture was one -- they were sibling directories each with
    their own `.git` directory, which the identity rule correctly reads as
    *separate repositories*. So the tests that claimed to cover "a ticket
    session writing to the trunk" never modelled it (#209).
    """
    root.mkdir(parents=True, exist_ok=True)
    entry = primary / ".git" / "worktrees" / root.name
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (entry / "gitdir").write_text(str(root / ".git") + "\n", encoding="utf-8")
    (root / ".git").write_text(f"gitdir: {entry}\n", encoding="utf-8")
    if ticket is not None:
        (root / CHAIN_DIR / str(ticket)).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def off_ticket(tmp_path: Path) -> Path:
    """
    The primary checkout, on the trunk.

    `.git` is a directory, which is what makes it the primary checkout rather
    than a worktree, so #209's gate applies to its source.
    """
    return _primary(tmp_path / "trunk", "dev")


@pytest.fixture
def repo(off_ticket: Path, tmp_path: Path) -> Path:
    """
    A genuine LINKED worktree on ticket 7's branch, with an empty chain.

    This used to be a bare directory holding its own `.git` *directory*, which
    is structurally a primary checkout: the fixture claimed to be a worktree
    and was not. Every test using it exercised a shape the repo never produces,
    and #209's report line correctly fired on it. Linked to `off_ticket`, the
    two are one repository, which is what they always claimed to be.
    """
    return _linked(off_ticket, tmp_path / "wt", "issue/7-x", 7)


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


def test_a_ticket_session_writing_to_the_trunk_is_refused(tmp_path: Path) -> None:
    """
    #206's row, now answered by #209's -- and the fixture had to be rebuilt.

    This used to pair two sibling directories each holding a `.git` directory,
    which the identity rule correctly reads as two separate repositories: the
    test claimed to cover "a Builder mid-ticket writing the trunk" and did not
    model it. With a genuine linked worktree the case is real, and the answer
    is now stronger than #206's: refused because nobody writes primary-checkout
    source, rather than judged against the session's chain.
    """
    main = _primary(tmp_path / "main", "dev")
    wt = _linked(main, tmp_path / "wt", "issue/7-x", 7)
    decision = decide_write(main / "botting" / "core.py", session=wt)
    assert not decision.allowed
    assert "primary checkout" in decision.reason


def test_the_target_s_ticket_wins_over_the_session_s(tmp_path: Path) -> None:
    """Row 1 before row 2: the file's own worktree is the better answer."""
    a = _worktree(tmp_path / "a", "issue/1-x", 1)
    b = _worktree(tmp_path / "b", "issue/2-x", 2)
    decision = decide_write(b / "botting" / "core.py", session=a)
    assert not decision.allowed
    assert "Ticket 2" in decision.reason


def test_neither_side_a_ticket_is_now_refused_in_the_primary(
    off_ticket: Path,
) -> None:
    """
    This asserted indifference, and it is the one test #209 inverts.

    Its fixture is a primary checkout on a non-ticket branch writing its own
    source, which is exactly the case this gate exists to refuse -- the
    orchestrator's seat. The old assertion was the hole, written down.
    """
    decision = decide_write(off_ticket / "botting" / "core.py", session=off_ticket)
    assert not decision.allowed
    assert "primary checkout" in decision.reason


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


# --- The primary checkout (#209) ---------------------------------------------
#
# #206 closed the case where the session sits outside the worktree it edits.
# This closes the case where NEITHER side is a ticket: the orchestrator's own
# seat, from which a write to a hard-stop path was allowed with no artifacts
# at all.


def test_identity_is_required_so_another_repository_is_never_refused(
    tmp_path: Path,
) -> None:
    """
    The finding that would have cost the most.

    Testing shape alone -- "is this not a linked worktree?" -- makes every git
    repository on the machine "the primary checkout", so another project's
    source is refused with a reason about this factory. #206 exists precisely
    because agents write other checkouts by absolute path.
    """
    mine = _primary(tmp_path / "mine", "dev")
    theirs = _primary(tmp_path / "OtherProject", "main")
    assert decide_write(theirs / "main.py", session=mine).allowed


def test_a_repository_whose_directory_is_named_worktrees_is_still_primary(
    tmp_path: Path,
) -> None:
    """
    The inverse failure: the gate silently off.

    Reading the resolved git dir's parent for the name `worktrees` answers
    False here, so a repository that happens to live in such a directory would
    be ungated. `.git` being a directory rather than a file does not care.
    """
    trap = _primary(tmp_path / "worktrees", "dev")
    assert _is_primary(trap)
    assert not decide_write(trap / "botting" / "core.py", session=trap).allowed


def test_a_linked_worktree_is_never_the_primary_checkout(tmp_path: Path) -> None:
    main = _primary(tmp_path / "main", "dev")
    wt = _linked(main, tmp_path / "wt", "issue/7-x", 7)
    assert _is_primary(main)
    assert not _is_primary(wt)
    assert _common(main) == _common(wt), "the same repository, though"


def test_a_ticket_branch_in_the_primary_checkout_is_still_refused(
    tmp_path: Path,
) -> None:
    """
    The bypass review found, and the reason no branch is consulted.

    Create a ticket branch in the primary (through the shell, which no hook
    sees), write intent.md, spec.md and spec-review.md -- all exempt, so all
    allowed -- and under a rule that deferred to the target's ticket, source
    writes are permitted again. Three permitted writes and one permitted
    command reopened the whole hole.
    """
    primary = _primary(tmp_path / "main", "issue/999-sneaky")
    chain = primary / CHAIN_DIR / "999"
    chain.mkdir(parents=True)
    for name in ("intent.md", "spec.md", "spec-review.md"):
        (chain / name).write_text(SPEC, encoding="utf-8")

    decision = decide_write(primary / "botting" / "core.py", session=primary)
    assert not decision.allowed
    assert "primary checkout" in decision.reason


def test_the_artifacts_stay_writable_in_the_primary(tmp_path: Path) -> None:
    """Refusing them is #189's deadlock: the gate forbidding its own remedy."""
    primary = _primary(tmp_path / "main", "dev")
    for exempt in (
        primary / CHAIN_DIR / "999" / "intent.md",
        primary / "docs" / "factory" / "stages.md",
        primary / "AGENTS.md",
    ):
        assert decide_write(exempt, session=primary).allowed, exempt


@pytest.mark.parametrize(
    "exempt",
    [
        "configs/game.ini",
        "configs/factory-models.toml",
        "profiles/mine.yaml",
        "toolkit/create_map.py",
        ".claude/settings.local.json",
    ],
)
def test_what_a_human_edits_in_their_own_checkout_stays_writable(
    tmp_path: Path, exempt: str
) -> None:
    """
    The settings passed into a launcher, the tools run by hand, and the escape
    hatch. `.claude/settings.local.json` is the sharp one: `OVERRIDE` tells the
    reader to write it, so refusing it is the gate refusing its own remedy.
    """
    primary = _primary(tmp_path / "main", "dev")
    assert decide_write(primary / exempt, session=primary).allowed


@pytest.mark.parametrize(
    "refused",
    [
        "botting/controller/inputs/focus.py",
        "maple/launchers/run.py",
        "factory/cli.py",
        "configs/maps/GhostShip1.json",
        ".claude/settings.json",
        "pyproject.toml",
        "CONTEXT.md",
    ],
)
def test_source_and_the_gates_themselves_are_refused(
    tmp_path: Path, refused: str
) -> None:
    """
    `maple/launchers/**` is source: a launcher imports the engine.
    `configs/maps/**` is a hard-stop path inside an exempt tree, so deny wins.
    `.claude/settings.json` holds the hooks, so exempting it would let an agent
    turn the gates off; only `settings.local.json` is exempt.
    """
    primary = _primary(tmp_path / "main", "dev")
    assert not decide_write(primary / refused, session=primary).allowed


@pytest.mark.parametrize(
    "tree", ["configs/game.ini", "profiles/x.yaml", "toolkit/t.py"]
)
def test_the_primary_exemptions_do_not_leak_into_a_ticket_worktree(
    tmp_path: Path, tree: str
) -> None:
    """
    The regression the obvious shortcut causes.

    Appending these to `_ALWAYS_WRITABLE_ROOTS` would be the one-line way to
    implement the exemption -- and that constant is shared with #206's gate, so
    the artifacts-before-code gate would silently lose three whole top-level
    trees inside ticket worktrees. Written before the matcher, because review
    predicted a Builder would reach for the shortcut first.
    """
    main = _primary(tmp_path / "main", "dev")
    wt = _linked(main, tmp_path / "wt", "issue/7-x", 7)
    decision = decide_write(wt / tree, session=wt)
    assert not decision.allowed, f"{tree} escaped the artifacts gate in a worktree"
    assert "spec.md" in decision.reason


def test_a_scratchpad_write_is_indifferent_whatever_the_session(
    tmp_path: Path,
) -> None:
    """
    The #206 over-reach, red against merged code.

    Its session row fired for *any* target, so `_always_writable` raised for an
    out-of-repo path, the chain was consulted, and a write to a temp file was
    refused whenever the session's chain was incomplete -- contradicting #206's
    own principle that the factory governs this repository, not the filesystem.
    """
    main = _primary(tmp_path / "repo", "dev")
    wt = _linked(main, tmp_path / "repo-wt", "issue/7-x", 7)
    loose = tmp_path / "scratch" / "notes.md"
    assert decide_write(loose, session=wt).allowed


def test_forcing_the_predicate_off_removes_every_primary_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The revert rehearsal, and the proof this rule is single-source.

    The maintainer accepted this friction provisionally, so reverting must be
    one edit. A test that counts references to a constant pins *syntax* and is
    satisfied by a copy-pasted literal at a second call site; forcing the one
    predicate off and finding no refusal survives proves single-source
    **control** instead, and survives refactors.
    """
    primary = _primary(tmp_path / "main", "dev")
    refused = ("botting/core.py", "maple/launchers/run.py", "configs/maps/m.json")
    assert all(
        not decide_write(primary / path, session=primary).allowed for path in refused
    ), "the gate must be refusing these before the rehearsal means anything"

    monkeypatch.setattr("factory.hooks._is_primary", lambda root: False)
    for path in refused:
        decision = decide_write(primary / path, session=primary)
        assert decision.allowed, f"{path} still refused with the predicate off"


def test_the_primary_checkout_is_warned_at_startup(off_ticket: Path) -> None:
    """
    The one mechanism that puts the rule in context *before* the agent acts.

    AGENTS.md, stages.md and the skill are lookups an agent must choose to
    make. Without this line the first refusal arrives as a bare deny, which is
    the "figure it out on its own" failure the rule was asked to avoid.
    """
    report = session_report(off_ticket, "dev")
    assert IN_PRIMARY in report
    assert report.startswith(HEARTBEAT)


def test_off_ticket_no_longer_claims_the_gates_only_apply_elsewhere(
    off_ticket: Path,
) -> None:
    """
    `OFF_TICKET` used to say the gates "still apply to files in one" -- a
    worktree -- which in the primary checkout reads as "files here are free",
    the opposite of the new rule. A correct line beside a wrong one is worse
    than no line, so the wrong clause is gone rather than joined.
    """
    assert "in one" not in session_report(off_ticket, "dev")


def test_a_ticket_branch_in_the_primary_is_warned_too(off_ticket: Path) -> None:
    """
    The ticket-branch path of the report needs the line as much as the other
    one, precisely because a ticket branch here is a refused state.
    """
    (off_ticket / CHAIN_DIR / "7").mkdir(parents=True)
    report = session_report(off_ticket, "issue/7-x")
    assert IN_PRIMARY in report
    assert "ticket 7" in report


def test_a_linked_worktree_is_not_warned(repo: Path) -> None:
    """The rule does not apply there, so saying it would be noise."""
    assert IN_PRIMARY not in session_report(repo, "issue/7-x")


def test_a_subdirectory_of_the_primary_is_still_warned(off_ticket: Path) -> None:
    """
    The report receives `Path.cwd()` while the gate walks up from the file. A
    session whose cwd is a subdirectory would otherwise get no line while its
    writes were refused -- the exact failure this line prevents.
    """
    deep = off_ticket / "maple" / "model"
    deep.mkdir(parents=True)
    assert IN_PRIMARY in session_report(deep, "dev")
