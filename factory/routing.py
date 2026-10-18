"""
Which stage a ticket is in, computed rather than judged.

An agent used to work this out from a table in the entry skill, which meant two
agents reading the same chain could reach different answers. That is the
randomness the factory exists to remove, so the table moves here and becomes a
function: same chain, same answer, every time.

The row order is the contract. **First match wins**, and a later row is never
preferred because it looks closer to where someone thinks the ticket is. A
chain with a gap in the middle therefore routes to the earliest unsatisfied
stage, not the latest artifact present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from factory.chain import Chain, read_chain, ticket_from_branch


class Stage(StrEnum):
    """The stages a ticket moves through. `stages.md` documents each one."""

    PLAN = "plan"
    DESIGN = "design"
    BUILD_PLANNING = "build-planning"
    BUILD_IMPLEMENTING = "build-implementing"
    TEST = "test"
    REVIEW = "review"
    QA = "qa"
    DOCUMENT = "document"
    INTEGRATE = "integrate"


@dataclass(frozen=True)
class Next:
    """
    What to do next on a ticket, and why.

    A set `blocked_by` means a person is needed: the caller exits 3 rather than
    carrying on. `stage` is None either because the branch names no ticket, or
    because the chain says stop.
    """

    ticket: int | None = None
    stage: Stage | None = None
    role: str | None = None
    section: str | None = None
    do: tuple[str, ...] = ()
    blocked_by: str | None = None
    artifact_missing: str | None = None
    note: str | None = None

    @property
    def blocked(self) -> bool:
        return self.blocked_by is not None


@dataclass(frozen=True)
class Row:
    """One row of the routing table: a condition, and where it sends you."""

    when: Callable[[Chain], bool]
    stage: Stage | None = None
    role: str | None = None
    section: str | None = None
    do: tuple[str, ...] = ()
    missing: str | None = None
    blocked_by: str | None = None
    #: Consulted only when the row matches, so the conditions stay readable.
    detail: Callable[[Chain], str] | None = None


#: The only verdicts a review or Run Report may record. `artifacts.md` carries
#: the same list. Anything else is a malformed artifact, not a third opinion.
VERDICTS: Final = frozenset({"pass", "changes-requested", "fail"})


class MalformedVerdict(ValueError):
    """An artifact recorded a verdict outside the contracted domain."""


def verdict_of(front: dict[str, str]) -> str:
    """
    A recorded verdict, lowercased and unquoted. Empty when none is recorded.

    Raises on an unrecognised value rather than guessing. Review found that
    treating an unknown verdict as either pass or fail silently decides the
    ticket, and both guesses are wrong in different ways.
    """
    found = front.get("verdict", "").strip().strip("\"'").lower()
    if found in {"", "null", "none"}:
        return ""
    if found not in VERDICTS:
        raise MalformedVerdict(
            f"verdict: {found!r} is not one of {sorted(VERDICTS)}. "
            f"A verdict outside the domain is a malformed artifact."
        )
    return found


def _incomplete(front: dict[str, str]) -> bool:
    """
    Whether a verdict file exists but records no verdict yet.

    This is NOT a failure. The file being present satisfies the row that
    demanded it, so an empty verdict used to fall through to the stop row and
    wedge the ticket at exit 3 — an unfinished review read as a rejected one.
    It routes back to that stage instead.
    """
    return verdict_of(front) == ""


#: The artifacts that, if present, mean real work has already been done.
_DOWNSTREAM: Final = ("plan.md", "review.md", "qa.md")


def _hole_upstream(chain: Chain) -> bool:
    """Whether an early artifact is missing while a later one exists."""
    missing_early = (
        "intent.md" not in chain.present
        or not chain.accepted
        or not chain.has_spec
        or not chain.has_spec_review
    )
    return missing_early and any(name in chain.present for name in _DOWNSTREAM)


def _describe_hole(chain: Chain) -> str:
    """Name the gap and the work that sits past it, so a person can judge."""
    gaps = [
        name
        for name, ok in (
            ("intent.md", "intent.md" in chain.present),
            ("intent.md: accepted_by", chain.accepted),
            ("spec.md", chain.has_spec),
            ("spec-review.md", chain.has_spec_review),
        )
        if not ok
    ]
    done = [name for name in _DOWNSTREAM if name in chain.present]
    return f"missing {', '.join(gaps)} but {', '.join(done)} already exist"


#: The routing table, in order. Taken from the entry skill's stub, which was
#: written deliberately and is the specification rather than a sketch.
ROWS: Final[tuple[Row, ...]] = (
    # FIRST, and it is a guard rather than a stage: a hole upstream with work
    # downstream is an inconsistent chain, not a stage to re-run.
    #
    # Without this, a ticket sitting at QA whose `spec-review.md` was never
    # committed routes to Design, and the Specifier rewrites the spec that the
    # plan, the implementation and a passing review were all contracted
    # against. Review found this; redoing is more destructive than stopping.
    Row(
        when=lambda c: _hole_upstream(c),
        blocked_by="the chain is inconsistent: work exists downstream of a gap",
        detail=_describe_hole,
    ),
    Row(
        when=lambda c: "intent.md" not in c.present or not c.accepted,
        stage=Stage.PLAN,
        role="Clerk",
        section="1 - Plan",
        do=("factory intent check <n>",),
        missing="intent.md: accepted_by",
    ),
    Row(
        when=lambda c: not c.has_spec or not c.has_spec_review,
        stage=Stage.DESIGN,
        role="Specifier, then Specification Reviewer",
        section="2 - Design",
        do=("factory spec check <n>",),
        detail=lambda c: "spec.md" if not c.has_spec else "spec-review.md",
    ),
    Row(
        when=lambda c: not c.has_plan,
        stage=Stage.BUILD_PLANNING,
        role="Builder",
        section="3 - Build, planning",
        do=("factory plan check <n>",),
        missing="plan.md",
    ),
    Row(
        when=lambda c: not c.has_proof,
        stage=Stage.BUILD_IMPLEMENTING,
        role="Builder",
        section="4 - Build, implementing; then 5 - Test",
        do=("factory prove red --test <nodeid>", "factory prove suite"),
        missing="plan.md: proof.suite",
    ),
    Row(
        when=lambda c: not c.has_review or _incomplete(c.review),
        stage=Stage.REVIEW,
        role="Reviewer",
        section="6 - Review",
        do=("factory review <n>",),
        missing="review.md: verdict",
    ),
    # A rejected review goes BACK TO THE BUILDER, it does not stop the ticket.
    # The stub table had only "stop and hand back" here, which made every
    # rejected review a manual rescue: nothing routed it back, so the ticket sat
    # at exit 3 until someone edited an artifact by hand.
    Row(
        when=lambda c: verdict_of(c.review) == "changes-requested",
        stage=Stage.BUILD_IMPLEMENTING,
        role="Builder",
        section="4 - Build, implementing; then 5 - Test",
        do=("address review.md, then record a fresh proof",),
        detail=lambda _: "review.md: changes-requested",
    ),
    Row(
        when=lambda c: c.has_qa and verdict_of(c.qa) == "changes-requested",
        stage=Stage.BUILD_IMPLEMENTING,
        role="Builder",
        section="4 - Build, implementing; then 5 - Test",
        do=("address qa.md, then record a fresh proof",),
        detail=lambda _: "qa.md: changes-requested",
    ),
    # `fail` is the irrecoverable one: a person decides what happens next.
    Row(
        when=lambda c: verdict_of(c.review) == "fail",
        blocked_by="review.md records a fail",
        detail=lambda _: "review.md verdict: fail",
    ),
    Row(
        when=lambda c: c.has_qa and verdict_of(c.qa) == "fail",
        blocked_by="qa.md records a fail",
        detail=lambda _: "qa.md verdict: fail",
    ),
    Row(
        when=lambda c: c.needs_qa and not c.has_qa,
        stage=Stage.QA,
        role="QA Operator",
        section="7 - QA",
        do=("factory client up --profile <qa-profile>", "factory qa run <n>"),
        missing="qa.md",
    ),
    Row(
        when=lambda c: c.plan.get("docs_cleared", "null") in {"", "null", "None"},
        stage=Stage.DOCUMENT,
        role="Documenter",
        section="8 - Document",
        do=("factory doc check <n>",),
        missing="plan.md: docs_cleared",
    ),
    Row(
        when=lambda _: True,
        stage=Stage.INTEGRATE,
        role="Integrator",
        section="9 - Integrate",
        do=("factory pr open <n>",),
    ),
)


def resolve(repo_root: Path, branch: str | None) -> Next:
    """
    The stage a ticket is in, from its chain alone.

    No network, no clock, no git beyond the branch name, so two callers on the
    same chain get the same answer. That is the whole point of the command.
    """
    ticket = ticket_from_branch(branch)
    if ticket is None:
        return Next(
            note="Not a ticket branch. AGENTS.md applies; the factory does not."
        )

    chain = read_chain(repo_root, ticket)
    for row in ROWS:
        if not row.when(chain):
            continue
        return Next(
            ticket=ticket,
            stage=row.stage,
            role=row.role,
            section=row.section,
            do=tuple(item.replace("<n>", str(ticket)) for item in row.do),
            blocked_by=row.blocked_by,
            artifact_missing=row.detail(chain) if row.detail else row.missing,
        )
    raise AssertionError("the last row matches everything")  # pragma: no cover
