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
    common_dir,
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
    "Not in a ticket worktree. A write is judged by the chain of the worktree "
    "the file lives in, so editing another worktree by absolute path is gated "
    "there (#206)."
)

#: Said whenever the session sits in the primary checkout, on any branch.
#:
#: This is the mechanism for "every agent knows before it is refused". The
#: other statements of the rule -- AGENTS.md, stages.md, the skill -- are
#: lookups an agent must choose to make; this one is in context before it
#: acts.
IN_PRIMARY = (
    "You are in the PRIMARY CHECKOUT, where no ticket governs anything, so "
    "source edits are REFUSED here (#209). Writable: configs/, profiles/, "
    "toolkit/, docs/, .factory/, AGENTS.md, .claude/settings.local.json -- "
    "not configs/maps/. Work happens on an issue/<n>-* branch in its own "
    "worktree: git worktree add ../<slug> -b issue/<n>-<slug>, and write the "
    "artifacts THERE, since `git worktree add` carries no uncommitted changes."
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

    Four rows, in order:

    1. The target is in this repository's **primary checkout** and is not
       exempt -> refused outright (#209). Nobody writes source there: not an
       orchestrator, not a Builder with a perfect chain.
    2. The target's own worktree is on a ticket branch -> judged against that
       worktree's chain (#206). The answer does not depend on where the session
       sits.
    3. The session is on a ticket branch and the target is **inside this
       repository** -> judged against the session's chain. Without this row a
       Builder mid-ticket could write source into another checkout unjudged.
    4. Otherwise indifferent: there is no ticket to judge against.

    Writes to the chain itself are always allowed, in whichever worktree they
    land. Refusing them would forbid the only action that could satisfy the
    gate, which is how a well-meaning hook becomes a deadlock.
    """
    #: Row 1 (#209). Ahead of everything, and consulting no branch: the
    #: primary checkout can be on a ticket branch, so deferring to the
    #: target's ticket left this gate open to the thing it exists to stop.
    refusal = _primary_refusal(target, session)
    if refusal is not None:
        return refusal

    found = governing(target)
    if found is not None and found.ticket is not None:
        return _judge(found.root, found.ticket, target)

    if session is None:
        return INDIFFERENT
    here = governing(session)
    if here is None or here.ticket is None:
        return INDIFFERENT
    #: Row 3 requires the target to be inside THIS repository. Without that,
    #: `_always_writable` raises for an out-of-repo path, the chain is
    #: consulted, and a write to a scratchpad file is refused whenever the
    #: session's chain is incomplete -- which contradicts #206's own principle
    #: that the factory governs this repository and not the filesystem.
    #: Verified against the merged code before changing it.
    if _common(here.root) is None or _common(here.root) != _common_of(target):
        return INDIFFERENT
    #: Accountable for what it writes anywhere in the repo, judged against its
    #: own chain, since the target's worktree has no ticket to offer.
    return _judge(here.root, here.ticket, target)


def _common_of(target: Path) -> Path | None:
    """The repository a target belongs to, or None when it is in none."""
    found = governing(target)
    return None if found is None else _common(found.root)


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
        return "\n".join([HEARTBEAT, OFF_TICKET, *_primary_lines(repo_root)])
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
    #: The ticket-branch path needs it too: the primary checkout can itself
    #: be on a ticket branch, and that is a refused state, not a safe one.
    lines.extend(_primary_lines(repo_root))
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


# --- The primary checkout: the one place no ticket governs anything (#209) ----
#
# #206 made a write judged by the worktree the file lives in, which left the
# case where NEITHER side is a ticket: a session in the primary checkout
# editing the primary checkout. That is the orchestrator's own seat, and a
# write to `botting/controller/inputs/` from it was allowed -- no intent, no
# spec, no review, no radius, on a hard-stop path.
#
# All work happens on an `issue/<n>-*` branch in its own worktree (AGENTS.md,
# bootstrap.md), so a direct source edit here is always wrong. Nothing has to
# be *distinguished* to know that, which is why this needs no role and no
# registration step -- a step that can be skipped is the failure being designed
# out.

#: Top-level trees a human legitimately edits in their own checkout: the
#: settings passed into a launcher, and the standalone tools they run.
#:
#: Deliberately **separate** from `_ALWAYS_WRITABLE_ROOTS`. Appending to that
#: one would share these exemptions with the #206 gate, so a write to
#: `<ticket worktree>/toolkit/x.py` with no `spec.md` would become allowed and
#: the artifacts-before-code gate would silently lose three whole trees. Review
#: found that; it is the shortcut this constant exists to refuse.
PRIMARY_EXEMPT: Final[tuple[tuple[str, ...], ...]] = (
    ("configs",),
    ("profiles",),
    ("toolkit",),
)

#: Refused inside an exempt tree. Deny wins over exempt.
#:
#: Map JSON is on the hard-stop list: recorded data movement depends on, and
#: among the few things no offline test can check. This blocks the hand-edit
#: path and nothing else -- maps are authored by a GUI writing files through a
#: Python process no hook sees, and a shell redirection still gets through
#: (#207). A speed bump, named as one.
PRIMARY_REFUSED: Final[tuple[tuple[str, ...], ...]] = (("configs", "maps"),)

#: Exempt by name, not by tree. `OVERRIDE` tells the reader to write
#: `FACTORY_HOOKS: off` here, so refusing it would mean the gate refuses the
#: write its own reason instructs -- #189's deadlock, in the seat where it bites
#: the maintainer rather than an agent.
#:
#: NOT all of `.claude/`: that holds the hooks and permissions themselves, and
#: #202 removed it from the merge policy's allowlist because an agent that can
#: edit it can disable the gates.
PRIMARY_EXEMPT_FILES: Final[tuple[tuple[str, ...], ...]] = (
    (".claude", "settings.local.json"),
)


def _common(root: Path) -> Path | None:
    """
    A repository's identity: its shared git directory.

    Equal for the primary checkout and every worktree linked to it, different
    for any other repository on the machine. Without this the gate refuses
    another project's source with a reason about the Legends factory -- and
    #206 exists precisely because agents write other checkouts by absolute
    path, so that is reachable rather than theoretical.
    """
    return common_dir(root)


def _is_primary(root: Path) -> bool:
    """
    Whether this is a primary checkout rather than a linked worktree.

    By **kind, not by path name**: a linked worktree's `.git` is a *file*
    holding a `gitdir:` pointer, a primary checkout's is a directory. Testing
    the resolved path's parent for `worktrees` instead reads `False` for a
    repository whose own directory happens to be named `worktrees` -- the gate
    silently off -- and `True` for a submodule, whose git dir sits under
    `modules/`.
    """
    return (root / ".git").is_dir()


def _matches(relative: Path, prefixes: tuple[tuple[str, ...], ...]) -> bool:
    """Whether a relative path starts with any of the given path prefixes."""
    parts = relative.parts
    return any(parts[: len(prefix)] == prefix for prefix in prefixes)


def _exempt_in_primary(root: Path, target: Path) -> bool:
    """
    Whether a primary-checkout path is one a human legitimately edits here.

    The **universal** exemptions come first. Without them `.factory/`, `docs/`
    and `AGENTS.md` are refused in the primary checkout, which is #189's
    deadlock exactly: the gate forbidding the artifact that would satisfy it,
    and forbidding the document describing its own escape hatch. Caught by
    `test_the_artifacts_stay_writable_in_the_primary` rather than by review,
    which is the order it should happen in.
    """
    if _always_writable(root, target):
        return True
    try:
        relative = target.resolve().relative_to(root.resolve())
    except ValueError, OSError:
        return False
    if _matches(relative, PRIMARY_REFUSED):
        return False
    return _matches(relative, PRIMARY_EXEMPT) or _matches(
        relative, PRIMARY_EXEMPT_FILES
    )


def _primary_refusal(target: Path, session: Path | None) -> Decision | None:
    """
    Row 1: nobody writes source in the primary checkout. `None` means this row
    does not apply.

    **No branch is consulted.** The primary checkout can itself be on a ticket
    branch, so a rule that deferred to the target's ticket left the gate open
    to exactly what it exists to stop: create a ticket branch here (through the
    shell, which no hook sees), write the three artifacts (exempt, so allowed),
    and source writes are permitted again. Review found that; three permitted
    writes and one permitted command reopened the whole hole.

    Consulting nothing is therefore the point, and it is also what makes this
    the single predicate the revert test switches off.
    """
    found = governing(target)
    if found is None or not _is_primary(found.root):
        return None
    #: Identity, not shape: without it, another project's checkout on this
    #: machine is refused with a reason about this repository's factory.
    #: Unestablishable identity fails open -- a gate that cannot tell whose
    #: repository a file belongs to must not invent an answer.
    if session is None:
        return None
    mine = _common(found.root)
    if mine is None or mine != _common(session):
        return None
    if _exempt_in_primary(found.root, target):
        return INDIFFERENT
    return Decision(allowed=False, reason=_primary_reason(found))


def _primary_reason(found: Governing) -> str:
    """
    What is refused, what is not, and what to do instead -- self-contained, so
    an agent that reaches it needs no second lookup.

    The base branch is read rather than named: the trunk could be renamed, or
    move from `movements-improvements` to `dev`, and nothing here should care.
    """
    base = found.branch or "HEAD"
    return (
        f"This is the primary checkout ({found.root.name}), where no ticket "
        f"governs anything, so source edits are refused. All work happens on "
        f"an issue/<n>-* branch in its own worktree (AGENTS.md, "
        f"docs/factory/bootstrap.md).\n"
        f"  Writable here: configs/, profiles/, toolkit/, docs/, .factory/, "
        f"AGENTS.md, .claude/settings.local.json. Not configs/maps/ -- a "
        f"hard-stop path.\n"
        f"  Instead:  git worktree add ../<slug> -b issue/<n>-<slug> {base}\n"
        f"  then write intent.md and spec.md IN THE NEW WORKTREE -- artifacts "
        f"written here stay behind, since `git worktree add` carries no "
        f"uncommitted changes.\n"
        f"  {OVERRIDE}"
    )


def _primary_lines(repo_root: Path) -> list[str]:
    """
    The awareness line, when the session sits in the primary checkout.

    The root is resolved through `governing()` rather than taken as given,
    because the report receives `Path.cwd()` while the gate walks up from the
    file. A session whose cwd is a subdirectory -- `<primary>/maple` -- would
    otherwise get no line at all while its writes were still refused, which is
    the "figure it out by being denied" failure this line exists to prevent.
    """
    found = governing(repo_root)
    if found is None or not _is_primary(found.root):
        return []
    return ["", IN_PRIMARY]
