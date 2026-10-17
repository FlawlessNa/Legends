"""
The decision table, exercised without the harness.

Every case here is a branch name plus a filesystem state, which is the whole
reason the decisions are pure functions: a hook that can only be tested by
triggering Claude Code is a hook nobody will dare change later.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.chain import read_chain, ticket_from_branch
from factory.hooks import decide_stop, decide_write, session_report

SPEC = "---\nticket: 7\nmethod: suite\n---\n\nbody\n"
PLAN_PROVEN = "---\nticket: 7\nsuite: pass\n---\n\nbody\n"
PLAN_UNPROVEN = "---\nticket: 7\nsuite: null\n---\n\nbody\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo root with an empty chain for ticket 7."""
    (tmp_path / ".factory" / "7").mkdir(parents=True)
    return tmp_path


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


def test_ordinary_branches_are_left_alone(repo: Path) -> None:
    """The hooks must be invisible off a ticket branch, or people disable them."""
    assert decide_write(repo, "dev", repo / "botting" / "core.py").allowed
    assert decide_stop(repo, "dev", source_changed=True).allowed
    assert session_report(repo, "dev") == ""


# --- The write gate ---------------------------------------------------------


def test_source_is_refused_before_a_spec_exists(repo: Path) -> None:
    decision = decide_write(repo, "issue/7-x", repo / "botting" / "core.py")
    assert not decision.allowed
    assert "spec.md" in decision.reason


def test_source_is_refused_while_the_spec_is_unreviewed(repo: Path) -> None:
    """A spec the Builder wrote and nobody checked is not a contract."""
    _write(repo, "spec.md", SPEC)
    decision = decide_write(repo, "issue/7-x", repo / "botting" / "core.py")
    assert not decision.allowed
    assert "spec-review.md" in decision.reason


def test_source_is_allowed_once_the_chain_is_in_order(repo: Path) -> None:
    _write(repo, "spec.md", SPEC)
    _write(repo, "spec-review.md", "---\nticket: 7\n---\n\nverdict\n")
    assert decide_write(repo, "issue/7-x", repo / "botting" / "core.py").allowed


@pytest.mark.parametrize(
    "target", [".factory/7/spec.md", ".factory/7/intent.md", ".factory/99/intent.md"]
)
def test_the_chain_itself_is_always_writable(repo: Path, target: str) -> None:
    """
    Refusing these would forbid the only action that satisfies the gate.

    That is how a well-meaning hook becomes a deadlock, so it is tested rather
    than trusted.
    """
    assert decide_write(repo, "issue/7-x", repo / target).allowed


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
    assert decide_write(repo, "issue/7-x", repo / target).allowed


@pytest.mark.parametrize(
    "target", ["botting/core.py", "tests/test_x.py", "factory/cli.py"]
)
def test_source_is_still_inside_the_gate(repo: Path, target: str) -> None:
    """Narrowing the deny must not empty it."""
    assert not decide_write(repo, "issue/7-x", repo / target).allowed


def test_the_reason_names_the_override(repo: Path) -> None:
    """A gate nobody can bypass in an emergency is a gate someone deletes."""
    decision = decide_write(repo, "issue/7-x", repo / "botting" / "core.py")
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
    _write(repo, "plan.md", f"---\nticket: 7\nsuite: {written}\n---\n")
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
