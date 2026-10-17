"""
The decisions the harness hooks make, as pure functions.

Every decision here is a function of a branch name and a filesystem state, and
returns a verdict rather than performing one. That is the whole design: a hook
whose logic can only be exercised by triggering the harness is a hook nobody
will change later, and the one thing worse than an unenforced rule is an
enforced rule nobody dares touch.

What this enforces is the *sequence*, not the *quality*. Checking that
`spec.md` exists before source is edited is a `stat`. Checking the spec is any
good needs a reviewer (#180). Do not mistake a green hook for a reviewed spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from factory.chain import CHAIN_DIR, Chain, read_chain, ticket_from_branch

#: The override, for the emergency these gates would otherwise own. A gate
#: nobody can bypass is a gate someone eventually deletes instead.
OVERRIDE = (
    "To bypass on this machine only, add to .claude/settings.local.json "
    '(gitignored): {"env": {"FACTORY_HOOKS": "off"}}'
)


@dataclass(frozen=True)
class Decision:
    """Allowed or not, and why. The reason is shown to the agent and the user."""

    allowed: bool
    reason: str = ""


#: Returned whenever the hooks have no opinion: not a ticket branch, or off.
INDIFFERENT = Decision(allowed=True)


#: Paths the gate never refuses. The chain, because refusing it would forbid the
#: only action that satisfies the gate. Documentation, because `intent.md` scopes
#: this gate to *source* -- and because a gate that forbids writing the file
#: documenting its own escape hatch is the deadlock this was meant to avoid,
#: which is exactly what the first implementation did until review caught it.
_ALWAYS_WRITABLE_ROOTS: Final = (CHAIN_DIR, "docs")

#: Instruction files, wherever they sit. Same reason.
_ALWAYS_WRITABLE_NAMES: Final = frozenset({"AGENTS.md", "CLAUDE.md"})


def _always_writable(repo_root: Path, target: Path) -> bool:
    """Whether a path falls outside the gate's scope and may be written anyway."""
    try:
        relative = target.resolve().relative_to(repo_root.resolve())
    except ValueError, OSError:
        return False
    if relative.parts[:1] and relative.parts[0] in _ALWAYS_WRITABLE_ROOTS:
        return True
    return relative.name in _ALWAYS_WRITABLE_NAMES


def decide_write(repo_root: Path, branch: str | None, target: Path) -> Decision:
    """
    Whether a write may proceed.

    Writes to the chain itself are always allowed. Refusing them would forbid
    the only action that could satisfy the gate, which is how a well-meaning
    hook turns into a deadlock.
    """
    ticket = ticket_from_branch(branch)
    if ticket is None:
        return INDIFFERENT
    if _always_writable(repo_root, target):
        return INDIFFERENT

    chain = read_chain(repo_root, ticket)
    if not chain.has_spec:
        return Decision(
            allowed=False,
            reason=(
                f"Ticket {ticket} has no .factory/{ticket}/spec.md. The artifacts come "
                f"before the code: write intent.md and spec.md and commit them alone "
                f"first (docs/factory/bootstrap.md, rule 3). {OVERRIDE}"
            ),
        )
    if not chain.has_spec_review:
        return Decision(
            allowed=False,
            reason=(
                f"Ticket {ticket} has no .factory/{ticket}/spec-review.md. A spec the "
                f"Builder wrote and nobody checked is not a contract. Have a reviewer "
                f"read spec.md against intent.md and record a verdict quoting at least "
                f"one criterion (docs/factory/stages.md, stage 2). {OVERRIDE}"
            ),
        )
    return INDIFFERENT


def decide_stop(repo_root: Path, branch: str | None, source_changed: bool) -> Decision:
    """
    Whether the agent may end its turn.

    Only blocks when source actually changed: a session that read code and
    answered a question owes no proof, and blocking it would train everyone to
    switch the hooks off.
    """
    ticket = ticket_from_branch(branch)
    if ticket is None or not source_changed:
        return INDIFFERENT

    chain = read_chain(repo_root, ticket)
    if not chain.has_plan:
        return Decision(
            allowed=False,
            reason=(
                f"Source changed on ticket {ticket} with no .factory/{ticket}/plan.md. "
                f"The plan names the files that change and the proof before the code "
                f"is written. {OVERRIDE}"
            ),
        )
    if not chain.has_proof:
        return Decision(
            allowed=False,
            reason=(
                f"Source changed on ticket {ticket} but plan.md records no proof. Run "
                f"the suite and record the outcome in proof.suite. Saying it passed is "
                f"not the same as having run it. {OVERRIDE}"
            ),
        )
    return INDIFFERENT


def session_report(repo_root: Path, branch: str | None) -> str:
    """
    What a session is told at startup. Never blocks; removes "I did not know".

    Empty for a non-ticket branch, so ordinary work is not narrated at.
    """
    ticket = ticket_from_branch(branch)
    if ticket is None:
        return ""
    chain = read_chain(repo_root, ticket)
    lines = [
        f"You are on a factory ticket branch: ticket {ticket}.",
        (
            "Read docs/factory/README.md, then follow the `factory` skill. "
            "Do not choose a stage yourself."
        ),
        "",
        f"Chain at .factory/{ticket}/:",
    ]
    lines.extend(_chain_lines(chain))
    if not chain.has_spec or not chain.has_spec_review:
        lines.append("")
        lines.append("Edits outside .factory/ will be REFUSED until those exist.")
    return "\n".join(lines)


def _chain_lines(chain: Chain) -> list[str]:
    """One line per artifact, present or missing, in stage order."""
    from factory.chain import ARTIFACTS

    out: list[str] = []
    for name in ARTIFACTS:
        mark = "present" if name in chain.present else "MISSING"
        out.append(f"  {name:<16} {mark}")
    if chain.has_plan:
        out.append(f"  proof recorded:  {'yes' if chain.has_proof else 'NO'}")
    return out
