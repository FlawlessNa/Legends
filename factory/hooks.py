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

from factory.chain import (
    CHAIN_DIR,
    Chain,
    current_branch,
    git_dir,
    read_chain,
    ticket_from_branch,
)

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


#: The proof-of-life every startup report opens with. An agent that does not see
#: this line is running with no gates at all, and is told to say so before
#: starting work -- because a dead hook and a permissive one look identical.
HEARTBEAT = "factory gates: LIVE"

#: Said at startup when the session is not in a ticket worktree. The gates are
#: live regardless, and they judge a file by *its* worktree, not by this one.
OFF_TICKET = (
    "Not in a ticket worktree. The gates still apply to files in one: a write "
    "is judged by the chain of the worktree the file lives in, so editing "
    "another worktree by absolute path is gated there (#206)."
)

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


def _always_writable(root: Path, target: Path) -> bool:
    """
    Whether a path falls outside the gate's scope and may be written anyway.

    `root` is the **governing** worktree, not the session's. Judged against the
    session's root instead, a write to another worktree's `.factory/` raises
    `ValueError` here and is not recognised as exempt -- so the first thing the
    new gate would refuse is the artifact write that satisfies it. That is the
    #189 deadlock, reintroduced through a side door by a fix for a different
    bug.

    Both sides are resolved. Comparing an unresolved root to a resolved target
    makes `relative_to` raise on Windows case-folding and 8.3 short names, with
    the same consequence.
    """
    try:
        relative = target.resolve().relative_to(root.resolve())
    except ValueError, OSError:
        return False
    if relative.parts[:1] and relative.parts[0] in _ALWAYS_WRITABLE_ROOTS:
        return True
    return relative.name in _ALWAYS_WRITABLE_NAMES


def _judge(root: Path, ticket: int, target: Path) -> Decision:
    """The sequence rules, against one worktree's chain."""
    if _always_writable(root, target):
        return INDIFFERENT
    chain = read_chain(root, ticket)
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


def decide_write(target: Path, session: Path | None = None) -> Decision:
    """
    Whether a write may proceed, decided from the file rather than the session.

    The gate applies when **either side is a ticket**:

    1. The target's own worktree is on a ticket branch -> judged against that
       worktree's chain. This is the fix: the answer no longer depends on where
       the session happens to sit.
    2. Otherwise, the session is on a ticket branch -> judged against the
       session's chain. Without this row a Builder mid-ticket could write
       source straight into the trunk checkout unjudged, which it cannot do
       today -- resolving from the target alone would have *loosened* the gate,
       which review caught the first draft asserting it did not do.
    3. Otherwise indifferent: there is no ticket to judge against.

    Writes to the chain itself are always allowed, in whichever worktree they
    land. Refusing them would forbid the only action that could satisfy the
    gate, which is how a well-meaning hook becomes a deadlock.
    """
    found = governing(target)
    if found is not None and found.ticket is not None:
        return _judge(found.root, found.ticket, target)

    if session is None:
        return INDIFFERENT
    here = governing(session)
    if here is None or here.ticket is None:
        return INDIFFERENT
    #: Row 2: accountable for what it writes anywhere, judged against its own
    #: chain, since the target's worktree has no ticket to offer.
    return _judge(here.root, here.ticket, target)


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

    Opens with `HEARTBEAT`, deliberately. Hooks fail open, so a hook that cannot
    run emits nothing at all -- and nothing it emits could report that. The only
    signal that survives is a line whose *presence* proves the toolchain is
    reachable. Its absence is what an agent is told to notice (#199).

    Empty for a non-ticket branch, so ordinary work is not narrated at.
    """
    ticket = ticket_from_branch(branch)
    if ticket is None:
        # The heartbeat still fires. A proof-of-life that only appears on ticket
        # branches is not proof: on the trunk, silence was indistinguishable
        # from the hooks being dead -- which is what #199 existed to make
        # visible, and what it still hid (#202).
        #
        # The second line is #206's. The write gate now judges a file by the
        # worktree it lives in, so a session here can still be refused -- for a
        # ticket it was never told it was working on. Without this the first
        # refusal arrives as a bare deny with no startup context, which is the
        # "I did not know" this report exists to remove.
        return f"{HEARTBEAT}\n{OFF_TICKET}"
    chain = read_chain(repo_root, ticket)
    lines = [
        HEARTBEAT,
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


# --- Which worktree governs a file -------------------------------------------
#
# The gates used to ask `ticket_from_branch(branch)` where `branch` was the
# SESSION's branch. A session on a non-ticket branch therefore made every write
# indifferent -- including writes into a ticket worktree squarely under the
# factory. That is how this factory was built: the session sits in the main
# checkout and edits a worktree by absolute path, and the gates were never once
# consulted. The artifacts did land before the code, but by discipline, which is
# the one thing this project exists to stop relying on (#206).


@dataclass(frozen=True)
class Governing:
    """The worktree a file belongs to, and what it is working on."""

    root: Path
    branch: str | None
    ticket: int | None


def _resolved(target: Path) -> Path | None:
    """
    An absolute, symlink-free target, or None if it cannot be made one.

    `resolve()` does not raise for a path that does not exist -- which is the
    normal `Write` case, a file being created -- but it can raise `OSError` or
    `ValueError` for a malformed one, and a hook that throws blocks every edit.
    """
    try:
        return target.resolve()
    except OSError, ValueError:
        return None


def governing(target: Path) -> Governing | None:
    """
    The worktree that governs a path, found without invoking git.

    `PreToolUse` fires on every edit, so this reads the filesystem rather than
    spawning a process, exactly as `current_branch` reads `HEAD` by hand.

    The stop condition is **an existing `.git` entry**, not a readable one. The
    alternative -- stopping only where `git_dir` resolves -- walks straight past
    a worktree whose `gitdir:` pointer is stale and attributes the file to some
    ancestor checkout instead. Stopping here and failing to read a branch is the
    honest answer, and it routes to indifferent on purpose: a detached `HEAD` is
    a legitimate state, and with no ticket there is nothing to refuse for.

    `None` means the path is under no worktree at all. The factory governs this
    repository, not the filesystem, so that is indifference rather than a
    failure -- otherwise every write to a scratchpad file would be refused.
    """
    resolved = _resolved(target)
    if resolved is None:
        return None
    #: Finite by construction. `while True: p = p.parent` does not terminate:
    #: on Windows `Path("C:/").parent` is itself.
    for candidate in (resolved, *resolved.parents):
        if not (candidate / ".git").exists():
            continue
        branch = current_branch(candidate) if git_dir(candidate) else None
        return Governing(
            root=candidate, branch=branch, ticket=ticket_from_branch(branch)
        )
    return None
