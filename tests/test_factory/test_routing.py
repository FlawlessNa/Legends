"""
Every row of the routing table, the order between them, and that it terminates.

The table used to live as prose in the entry skill, where two agents reading the
same chain could reach different answers. These tests are what make "computed,
not judged" true rather than claimed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.routing import MalformedVerdict, Next, Stage, resolve

TICKET = 7
BRANCH = f"issue/{TICKET}-slug"

ACCEPTED = "---\nticket: 7\naccepted_by: nassim\n---\n"
UNACCEPTED = "---\nticket: 7\naccepted_by: null\n---\n"


def _spec(method: str = "suite") -> str:
    return f"---\nticket: 7\nmethod: {method}\n---\n"


def _plan(suite: str = "pass", docs: str = "[]") -> str:
    return f"---\nticket: 7\nsuite: {suite}\ndocs_cleared: {docs}\n---\n"


def _verdict(value: str) -> str:
    return f"---\nticket: 7\nverdict: {value}\n---\n"


@pytest.fixture
def chain(tmp_path: Path) -> Path:
    (tmp_path / ".factory" / str(TICKET)).mkdir(parents=True)
    return tmp_path


def _write(root: Path, name: str, text: str) -> None:
    (root / ".factory" / str(TICKET) / name).write_text(text, encoding="utf-8")


def _drop(root: Path, name: str) -> None:
    (root / ".factory" / str(TICKET) / name).unlink()


def _complete(root: Path, method: str = "suite") -> None:
    """Every artifact a finished ticket of this method should carry."""
    _write(root, "intent.md", ACCEPTED)
    _write(root, "spec.md", _spec(method))
    _write(root, "spec-review.md", _verdict("pass"))
    _write(root, "plan.md", _plan())
    _write(root, "review.md", _verdict("pass"))
    if method in {"live", "both"}:
        _write(root, "qa.md", _verdict("pass"))


def _at(root: Path) -> Next:
    return resolve(root, BRANCH)


# --- The rows, in order -----------------------------------------------------


def test_an_empty_chain_starts_at_plan(chain: Path) -> None:
    assert _at(chain).stage is Stage.PLAN


def test_an_unaccepted_intent_is_still_plan(chain: Path) -> None:
    """`accepted_by: null` is the schema's own word for 'not yet'."""
    _write(chain, "intent.md", UNACCEPTED)
    assert _at(chain).stage is Stage.PLAN


@pytest.mark.parametrize("missing", ["spec.md", "spec-review.md"])
def test_design_until_both_the_spec_and_its_review_exist(
    chain: Path, missing: str
) -> None:
    _write(chain, "intent.md", ACCEPTED)
    _write(chain, "spec.md", _spec())
    _write(chain, "spec-review.md", _verdict("pass"))
    _drop(chain, missing)
    step = _at(chain)
    assert step.stage is Stage.DESIGN
    assert step.artifact_missing == missing


def test_an_unfilled_proof_block_means_build(chain: Path) -> None:
    _complete(chain)
    _write(chain, "plan.md", _plan(suite="null"))
    assert _at(chain).stage is Stage.BUILD_IMPLEMENTING


def test_a_complete_suite_ticket_reaches_integrate(chain: Path) -> None:
    _complete(chain)
    assert _at(chain).stage is Stage.INTEGRATE


# --- Termination: the defect the review found -------------------------------


@pytest.mark.parametrize("method", ["suite", "live", "both", "assent"])
def test_every_method_can_reach_integrate(chain: Path, method: str) -> None:
    """
    A routing table with no fixed point wedges a ticket forever.

    Review found that a `method: live` ticket could match the build row on every
    invocation, leaving review, QA, document and integrate unreachable. This
    asserts a terminal row exists for every legal method rather than trusting
    that one does.
    """
    _complete(chain, method)
    assert _at(chain).stage is Stage.INTEGRATE


def test_a_live_ticket_waits_for_its_run_report(chain: Path) -> None:
    _complete(chain, "live")
    _drop(chain, "qa.md")
    assert _at(chain).stage is Stage.QA


def test_a_suite_ticket_never_asks_for_qa(chain: Path) -> None:
    """QA is skipped entirely when nothing about the ticket is live."""
    _complete(chain, "suite")
    assert _at(chain).stage is not Stage.QA


# --- Verdicts ---------------------------------------------------------------


def test_a_rejected_review_goes_back_to_the_builder(chain: Path) -> None:
    """
    Not a dead end.

    The stub table said only "stop and hand back" here, which made every
    rejected review a manual rescue: nothing routed it back, so the ticket sat
    blocked until a human edited an artifact by hand.
    """
    _complete(chain)
    _write(chain, "review.md", _verdict("changes-requested"))
    step = _at(chain)
    assert step.stage is Stage.BUILD_IMPLEMENTING
    assert not step.blocked


def test_a_failed_review_stops_the_ticket(chain: Path) -> None:
    _complete(chain)
    _write(chain, "review.md", _verdict("fail"))
    assert _at(chain).blocked


def test_an_unfinished_review_routes_to_review_not_to_stop(chain: Path) -> None:
    """
    An incomplete artifact is not a rejection.

    `review.md` present with no verdict used to read as "anything but a pass"
    and wedge the ticket, when the right answer is "finish the review".
    """
    _complete(chain)
    _write(chain, "review.md", "---\nticket: 7\n---\n")
    step = _at(chain)
    assert step.stage is Stage.REVIEW
    assert not step.blocked


def test_an_unrecognised_verdict_is_an_error_not_a_guess(chain: Path) -> None:
    """Guessing either way silently decides the ticket, and both guesses hurt."""
    _complete(chain)
    _write(chain, "review.md", _verdict("needs-discussion"))
    with pytest.raises(MalformedVerdict):
        _at(chain)


# --- The guard against destructive backwards routing ------------------------


def test_a_gap_upstream_with_work_downstream_stops(chain: Path) -> None:
    """
    Redoing is more destructive than stopping.

    A ticket at QA whose `spec-review.md` was never committed used to route to
    Design, where the Specifier rewrites the spec that the plan, the
    implementation and a passing review were all contracted against.
    """
    _complete(chain, "live")
    _drop(chain, "spec-review.md")
    step = _at(chain)
    assert step.blocked
    assert "spec-review.md" in (step.artifact_missing or "")


def test_a_reopened_intent_with_work_downstream_stops(chain: Path) -> None:
    _complete(chain)
    _write(chain, "intent.md", UNACCEPTED)
    assert _at(chain).blocked


def test_the_guard_does_not_fire_on_an_ordinary_early_ticket(chain: Path) -> None:
    """It must only catch a hole, never an unfinished beginning."""
    _write(chain, "intent.md", ACCEPTED)
    assert not _at(chain).blocked


# --- Order, and branches that are not tickets -------------------------------


def test_the_first_matching_row_wins(chain: Path) -> None:
    """
    A chain matching two rows takes the earlier one.

    Here `plan.md` is missing (an early row) and so is `review.md` (a later
    one). Preferring the later row because its artifact looks closer to done is
    the error the ordering exists to prevent.
    """
    _write(chain, "intent.md", ACCEPTED)
    _write(chain, "spec.md", _spec())
    _write(chain, "spec-review.md", _verdict("pass"))
    assert _at(chain).stage is Stage.BUILD_PLANNING


@pytest.mark.parametrize("branch", ["dev", "movements-improvements", None])
def test_a_non_ticket_branch_is_not_an_error(chain: Path, branch: str | None) -> None:
    step = resolve(chain, branch)
    assert step.stage is None
    assert step.ticket is None
    assert not step.blocked
    assert step.note is not None


def test_the_same_chain_always_gives_the_same_answer(chain: Path) -> None:
    """The whole point: computed, not judged."""
    _complete(chain, "both")
    _drop(chain, "qa.md")
    assert _at(chain) == _at(chain)
