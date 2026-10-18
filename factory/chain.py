"""
Reading a ticket's artifact chain.

Deliberately dependency-free. `pyproject.toml` declares `dependencies = []` so
that packaging the factory never becomes a second place the project's
dependencies are pinned, and the hooks that import this run on every edit — a
YAML parser would be both a dependency and a cost.

Only scalar front-matter is understood: `key: value` at the top level of the
leading `---` block. That is all any gate needs, and a reader that quietly
half-understands a nested structure is worse than one that does not try.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: `issue/133-some-slug` -> 133. The branch name is the only place a session is
#: told which ticket it is on, so this pattern is load-bearing.
_BRANCH = re.compile(r"^issue/(\d+)(?:-|$)")

#: A scalar entry in a front-matter block. Nested keys are skipped, not guessed.
_SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")

#: Where chains live, relative to the repo root.
CHAIN_DIR: Final = ".factory"

#: The files a chain may hold, in stage order.
ARTIFACTS: Final = (
    "intent.md",
    "spec.md",
    "spec-review.md",
    "plan.md",
    "qa.md",
    "review.md",
)


def ticket_from_branch(branch: str | None) -> int | None:
    """The ticket a branch names, or None when the branch is not a ticket branch."""
    if not branch:
        return None
    found = _BRANCH.match(branch.strip())
    return int(found.group(1)) if found else None


def _git_dir(repo_root: Path) -> Path | None:
    """
    The directory holding `HEAD`, for a normal checkout or a linked worktree.

    In a worktree `.git` is a *file* containing `gitdir: <path>`, not a
    directory — so the obvious `repo_root / ".git" / "HEAD"` silently finds
    nothing and every gate reports "not a ticket branch". That matters because
    `factory claim` gives each ticket its own worktree, which is precisely where
    the gates are supposed to run (#199).
    """
    git = repo_root / ".git"
    if git.is_dir():
        return git
    try:
        text = git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "gitdir: "
    if not text.startswith(prefix):
        return None
    resolved = Path(text[len(prefix) :].strip())
    if not resolved.is_absolute():
        resolved = (repo_root / resolved).resolve()
    return resolved if resolved.is_dir() else None


def current_branch(repo_root: Path) -> str | None:
    """
    The checked-out branch, read from `HEAD` rather than by running git.

    This is called from `PreToolUse`, which fires on every edit, so spawning a
    process would be paid hundreds of times a session.
    """
    git_dir = _git_dir(repo_root)
    if git_dir is None:
        return None
    try:
        text = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    return text[len(prefix) :] if text.startswith(prefix) else None


def front_matter(path: Path) -> dict[str, str]:
    """
    The scalar front-matter of a markdown file, empty when there is none.

    A missing file and a file without front-matter are the same answer on
    purpose: both mean "this artifact does not tell us anything", and a gate
    that distinguishes them would be asserting something it cannot know.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    body, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    found: dict[str, str] = {}
    for line in body.splitlines():
        if line.startswith((" ", "\t", "-", "#")) or not line.strip():
            continue
        match = _SCALAR.match(line)
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


@dataclass(frozen=True)
class Chain:
    """What a ticket's `.factory/<n>/` directory currently holds."""

    ticket: int
    root: Path
    present: frozenset[str]
    spec: dict[str, str]
    plan: dict[str, str]
    review: dict[str, str]
    qa: dict[str, str]
    intent: dict[str, str]

    @property
    def has_spec(self) -> bool:
        return "spec.md" in self.present

    @property
    def has_spec_review(self) -> bool:
        return "spec-review.md" in self.present

    @property
    def has_plan(self) -> bool:
        return "plan.md" in self.present

    @property
    def accepted(self) -> bool:
        """
        Whether the intent has been accepted by a person.

        `null` is the schema's own word for "not yet", so it counts as absent.
        """
        return self.intent.get("accepted_by", "null") not in {"", "null", "None"}

    @property
    def has_qa(self) -> bool:
        return "qa.md" in self.present

    @property
    def has_review(self) -> bool:
        return "review.md" in self.present

    @property
    def needs_qa(self) -> bool:
        """Whether `spec.md`'s method calls for a Run Report at all."""
        return self.spec.get("method", "") in {"live", "both"}

    @property
    def has_proof(self) -> bool:
        """
        Whether the plan records a proof outcome.

        `null` is how an unfilled proof block is written, so it counts as
        absent — the string is the schema's own word for "not yet".
        """
        value = self.plan.get("suite", "null")
        return value not in {"", "null", "None"}


def read_chain(repo_root: Path, ticket: int) -> Chain:
    """Read the chain for one ticket. Missing files are absent, never an error."""
    root = repo_root / CHAIN_DIR / str(ticket)
    present = frozenset(name for name in ARTIFACTS if (root / name).is_file())
    return Chain(
        ticket=ticket,
        root=root,
        present=present,
        spec=front_matter(root / "spec.md"),
        plan=front_matter(root / "plan.md"),
        review=front_matter(root / "review.md"),
        qa=front_matter(root / "qa.md"),
        intent=front_matter(root / "intent.md"),
    )
