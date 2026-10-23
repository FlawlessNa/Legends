"""
Reading a ticket's artifact chain.

Deliberately dependency-free. `pyproject.toml` declares `dependencies = []` so
that packaging the factory never becomes a second place the project's
dependencies are pinned, and the hooks that import this run on every edit — a
YAML parser would be both a dependency and a cost.

Scalar front-matter is read by `front_matter`: `key: value` at the top level of
the leading `---` block. Lists of scalars are read separately, by
`front_matter_lists`. Anything nested deeper is not read at all, because a
reader that quietly half-understands a nested structure is worse than one that
does not try.
"""

from __future__ import annotations

import re
import subprocess
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

#: The files the factory loop's chains add (design.md §6). Tracked apart from
#: `ARTIFACTS` because `session_report` prints a line per `ARTIFACTS` name, and
#: a v1 session should not be told it is missing five files it never needs.
LOOP_ARTIFACTS: Final = (
    "acceptance.md",
    "proof.md",
    "answers.md",
    "park.md",
    "run.md",
)

#: A list item that is itself a mapping: `- id: x`, or `- id:`. Prose that
#: merely contains `: ` mid-sentence is not one -- real criteria do that.
_MAPPING_ITEM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:(\s|$)")

#: The two radius forms, named in every refusal so the fix is in the message.
_RADIUS_FORMS = "allowed forms are 'path/to/file' and 'path/to/dir/**'"

#: The chain versions this reader understands, by the spelling `intent.md` uses.
_VERSIONS: Final = {"1": 1, "2": 2}


class UnknownChainVersion(ValueError):
    """`intent.md` names a chain version this reader does not know."""


def ticket_from_branch(branch: str | None) -> int | None:
    """The ticket a branch names, or None when the branch is not a ticket branch."""
    if not branch:
        return None
    found = _BRANCH.match(branch.strip())
    return int(found.group(1)) if found else None


def git_dir(repo_root: Path) -> Path | None:
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


def common_dir(repo_root: Path) -> Path | None:
    """
    A repository's identity: its shared git directory, or None outside one.

    Equal for the primary checkout and every worktree linked to it, different
    for any other repository. **Decided by the shape of `.git`, never by a
    folder's name**: a primary checkout has a `.git` directory and is its own
    answer, even when it sits in a folder called `worktrees`. A linked worktree
    names its shared directory in the `commondir` file of its git directory. With
    no such file -- a hand-built fixture, but also a submodule or a
    `--separate-git-dir` checkout, which git gives none -- only the layout
    `<common>/worktrees/<name>` counts as a linked worktree; anything else is
    its own repository.
    """
    found = git_dir(repo_root)
    if found is None:
        return None
    if (repo_root / ".git").is_dir():
        return found
    try:
        text = (found / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        common = Path(text)
        return common if common.is_absolute() else (found / common).resolve()
    return found.parent.parent if found.parent.name == "worktrees" else found


def current_branch(repo_root: Path) -> str | None:
    """
    The checked-out branch, read from `HEAD` rather than by running git.

    This is called from `PreToolUse`, which fires on every edit, so spawning a
    process would be paid hundreds of times a session.
    """
    found = git_dir(repo_root)
    if found is None:
        return None
    try:
        text = (found / "HEAD").read_text(encoding="utf-8").strip()
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

    One level of nesting is flattened to a dotted key, because the schema uses
    it: `artifacts.md` contracts `plan.md`'s `proof` as an object, so the field
    a gate wants is `proof.suite`. Read as top-level keys only that field was
    invisible and `has_proof` could never be true, which would have wedged
    every real ticket at build-implementing. Lists stay unread: nothing gates
    on one yet.
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
    parent = ""
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith(("-", "#")):
            continue
        indented = line.startswith((" ", "\t"))
        match = _SCALAR.match(line.strip() if indented else line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if indented:
            if parent:
                found[f"{parent}.{key}"] = value
            continue
        found[key] = value
        #: An empty value opens a block: the indented keys under it belong
        #: to it, and anything else closes it again.
        parent = key if value == "" else ""
    return found


def _front_block(path: Path) -> str | None:
    """The text between the leading `---` lines, or None when there is none."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    _, _, rest = text.partition("\n")
    body, sep, _ = rest.partition("\n---")
    return body if sep else None


def front_matter_lists(path: Path) -> dict[str, tuple[str, ...]]:
    """
    The top-level lists of scalars in a file's front-matter.

    Two spellings: a block list (`key:` then indented `- item` lines, up to the
    next non-blank, non-comment line at column 0) and a flow list (`key: []`,
    `key: [a, b]`). Blank lines and whole-line `#` comments are skipped wherever
    they sit, column 0 included. Items keep their quotes, and a trailing
    `# comment` stays part of its item: nothing here unquotes or strips, so
    nothing here can do either wrongly.

    `key:` with no items is YAML's null, not an empty list, so it is absent;
    `key: []` is the empty list. A key that appears twice takes its last
    occurrence, as `front_matter` does.

    **A key is absent rather than half-read** when any item is a mapping
    (`- id: x`) or a nested list (`- - a`), when its items are not indented, or
    when their indentation differs (compared literally, so a tab is not a
    space), or when it holds any indented line that is not an item -- all of
    which mean a structure this reader does not try to understand.
    """
    body = _front_block(path)
    if body is None:
        return {}
    found: dict[str, tuple[str, ...]] = {}
    key: str | None = None
    items: list[str] = []
    prefix: str | None = None
    broken = False

    for line in [*body.splitlines(), "\x00"]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            if key is not None and stripped.startswith("-"):
                #: An item at column 0 is valid YAML, but not this grammar.
                broken = True
                continue
            #: Column 0 closes whatever list was open, then may open the next.
            if key is not None and not broken and items:
                found[key] = tuple(items)
            key, items, prefix, broken = None, [], None, False
            match = _SCALAR.match(line)
            if not match:
                continue
            name, value = match.group(1), match.group(2).strip()
            found.pop(name, None)
            if value == "":
                key = name
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                found[name] = (
                    tuple(p.strip() for p in inner.split(",")) if inner else ()
                )
            continue
        if key is None or broken:
            continue
        if not (stripped == "-" or stripped.startswith("- ")):
            broken = True
            continue
        lead = line[: len(line) - len(line.lstrip())]
        if prefix is None:
            prefix = lead
        elif lead != prefix:
            broken = True
            continue
        item = stripped[1:].strip()
        if _MAPPING_ITEM.match(item) or item == "-" or item.startswith("- "):
            broken = True
            continue
        items.append(item)
    return found


def radius_errors(entries: tuple[str, ...]) -> tuple[str, ...]:
    """
    One message per radius entry this reader could not compare with another.

    Two forms only: a file path, or a directory followed by `/**`, relative and
    POSIX. Overlap between two such entries is a prefix comparison; a general
    glob against a general glob is not decidable with what the factory has
    (design.md re-check d), and a radius lock that cannot compare must not guess.
    """
    return tuple(
        f"radius entry {entry!r} is not allowed: {_RADIUS_FORMS}"
        for entry in entries
        if not _valid_radius(entry)
    )


def _valid_radius(entry: str) -> bool:
    path = entry.removesuffix("/**")
    if not path or "\\" in entry:
        return False
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return False
    if any(char in path for char in "*?["):
        return False
    return all(segment not in {"", ".", ".."} for segment in path.split("/"))


def blob(repo_root: Path, commit: str, relpath: str) -> str | None:
    """
    Git's content id for one file at one commit, or None when there is none.

    The id git computed after its own line-ending normalisation, so the same
    content gives the same answer whether it was checked out with CRLF or LF --
    which hashing the working file does not (`core.autocrlf=true`, review M7).

    `relpath` is POSIX and relative to the repo root. A missing commit, a
    missing path, a directory, and git itself being unavailable all answer
    None: an absent artifact is absent, never an error. No hook calls this; it
    spawns a process.

    `ls-tree`, not `rev-parse <commit>:<path>^{blob}`: the peel is read as part
    of the path and fails for every file (verified on git 2.39.1). Its output
    is read as raw `-z` records, so git never quotes a path (non-ASCII, a
    quote, a tab), and decoded here as UTF-8 rather than in the
    console's codepage. `--end-of-options` keeps a `commit` beginning with `-`
    from being read as a flag.
    """
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-tree",
                "-z",
                "--end-of-options",
                commit,
                "--",
                relpath,
            ],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    for record in done.stdout.split(b"\0"):
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split()
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if len(parts) == 3 and parts[1] == b"blob" and path == relpath:
            return parts[2].decode("ascii")
    return None


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
    spec_review: dict[str, str]
    acceptance: dict[str, str]
    #: `proof.md`'s front matter, which the factory loop writes. Not the same
    #: thing as `has_proof`, which reads v1's `plan.md` `proof.suite`.
    proof: dict[str, str]
    answers: dict[str, str]
    park: dict[str, str]
    #: `front_matter_lists` per artifact name.
    lists: dict[str, dict[str, tuple[str, ...]]]

    @property
    def criteria(self) -> tuple[str, ...]:
        """`spec.md`'s criteria, empty when absent or unreadable."""
        return self.lists.get("spec.md", {}).get("criteria", ())

    @property
    def radius(self) -> tuple[str, ...]:
        """`plan.md`'s radius, empty when absent or unreadable."""
        return self.lists.get("plan.md", {}).get("radius", ())

    @property
    def version(self) -> int:
        """
        1 for every chain written before the factory loop; 2 from `chain: 2`.

        An unrecognised value raises rather than guessing, for the same reason
        an unrecognised verdict does: either guess silently decides how the
        ticket is routed.
        """
        if "chain" not in self.intent:
            return 1
        value = self.intent["chain"]
        if value not in _VERSIONS:
            raise UnknownChainVersion(
                f".factory/{self.ticket}/intent.md: chain: {value!r} is not one of "
                f"{', '.join(sorted(_VERSIONS))}."
            )
        return _VERSIONS[value]

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

        The field is `proof.suite`, not `suite`: `artifacts.md` contracts
        `proof` as an object holding `red_test`, `red_output_sha` and `suite`,
        and every real `plan.md` writes it that way.

        This is v1's proof, written by the Builder. A v2 chain's proof is
        `proof.md`, written by the factory loop, and read as `Chain.proof`.
        """
        value = self.plan.get("proof.suite", "null")
        return value not in {"", "null", "None"}


def read_chain(repo_root: Path, ticket: int) -> Chain:
    """Read the chain for one ticket. Missing files are absent, never an error."""
    root = repo_root / CHAIN_DIR / str(ticket)
    present = frozenset(
        name for name in (*ARTIFACTS, *LOOP_ARTIFACTS) if (root / name).is_file()
    )
    return Chain(
        ticket=ticket,
        root=root,
        present=present,
        spec=front_matter(root / "spec.md"),
        plan=front_matter(root / "plan.md"),
        review=front_matter(root / "review.md"),
        qa=front_matter(root / "qa.md"),
        intent=front_matter(root / "intent.md"),
        spec_review=front_matter(root / "spec-review.md"),
        acceptance=front_matter(root / "acceptance.md"),
        proof=front_matter(root / "proof.md"),
        answers=front_matter(root / "answers.md"),
        park=front_matter(root / "park.md"),
        lists={name: front_matter_lists(root / name) for name in sorted(present)},
    )
