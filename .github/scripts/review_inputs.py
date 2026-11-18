"""Write the inputs of the Claude review of an epic PR into a directory.

`.github/workflows/claude-review.yml` runs this before Claude starts, with the
job's GITHUB_TOKEN. Claude then reads only these files and the checkout
around them: it has no shell and no network tools.

Everything about the PR comes in through the environment, never through the
command line or a workflow expression:

- REPO: `owner/name`.
- PR: the PR number.
- BASE_REF: the branch the PR targets, as the event reported it.
- HEAD_SHA: the commit under review, as the event reported it.
- GH_TOKEN: optional. Used by `gh` and, when set, for `git fetch`.

The ticket the PR closes and the epic the ticket is part of are included only
when their author is the repo's OWNER, a MEMBER or a COLLABORATOR, and with only
the comments by those. Anyone on GitHub can comment on an issue, so other text
never reaches the review.

A PR that merges the default branch (dev) into an epic has no ticket: its body
names the epic on an `Epic: #<n>` line instead, and that epic is fetched under
the same rule. Whether the PR really is such a merge is worked out from git
alone, and written into `dev-merge.md` with the evidence: the merge commits that
bring dev in, and the PR's own commits that are not on dev, which are the
changes the review must judge closely.

Usage: python .github/scripts/review_inputs.py <output directory>
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

TRUSTED = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

# GitHub's closing keywords. re.ASCII: `[0-9]` only, never another script's digits.
_CLOSES = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+#([0-9]+)\b",
    re.IGNORECASE | re.ASCII,
)
_PART_OF = re.compile(r"\bPart of #([0-9]+)\b", re.IGNORECASE | re.ASCII)
# A dev-merge PR's line naming its epic, at the start of a line.
_EPIC_LINE = re.compile(
    r"^[ \t]*Epic:[ \t]*#([0-9]+)\b", re.IGNORECASE | re.ASCII | re.MULTILINE
)
_EPIC_REF = re.compile(r"epic/[A-Za-z0-9._/-]+", re.ASCII)
_BRANCH = re.compile(r"[A-Za-z0-9._/-]+", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
_DIGITS = re.compile(r"[0-9]+", re.ASCII)


def ticket_number(pr_body: str) -> int | None:
    """The issue the PR body closes (`Closes #<n>`), the first one if several."""
    match = _CLOSES.search(pr_body)
    return int(match.group(1)) if match else None


def epic_number(ticket_body: str) -> int | None:
    """The epic a ticket names on its `Part of #<n>` line."""
    match = _PART_OF.search(ticket_body)
    return int(match.group(1)) if match else None


def named_epic(pr_body: str) -> int | None:
    """The epic a dev-merge PR names on its `Epic: #<n>` line, the first if several."""
    match = _EPIC_LINE.search(pr_body)
    return int(match.group(1)) if match else None


def is_trusted(item: dict[str, Any]) -> bool:
    """Whether an issue or comment was written by the repo's own people."""
    return item.get("author_association") in TRUSTED


def valid_base_ref(ref: str) -> bool:
    """An epic branch name, with nothing git could read as an option or range."""
    return bool(_EPIC_REF.fullmatch(ref)) and ".." not in ref and not ref.endswith("/")


def valid_branch(ref: str) -> bool:
    """A branch name, with nothing git could read as an option or range."""
    return (
        bool(_BRANCH.fullmatch(ref))
        and not ref.startswith(("-", "/"))
        and ".." not in ref
        and not ref.endswith("/")
    )


@dataclass(frozen=True)
class DiffFile:
    """One file's section of a unified diff: where it starts, and its header."""

    start: int
    lines: int
    header: str


def index_diff(lines: list[str]) -> list[DiffFile]:
    """Each file's section of `git diff` output, by 1-based line number.

    A section starts at its `diff --git ` line. Content lines start with a
    space, `+`, `-` or `\\`, so a header is never confused with content.
    """
    starts = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    bounds = [*starts, len(lines)]
    return [
        DiffFile(start + 1, bounds[n + 1] - start, lines[start].rstrip("\n"))
        for n, start in enumerate(starts)
    ]


# The tree at the reviewed commit is written as plain files, for context the
# diff does not show. Only what cannot lead anywhere else is written.
REGULAR_MODES = frozenset({b"100644", b"100755"})
MAX_TREE_FILE = 1_000_000


def tree_skip_reason(mode: bytes, size: int, path: str) -> str | None:
    """Why a tree entry is listed rather than written, or None to write it.

    A link could point outside the workspace and a submodule has no content
    here. A path is written only if it stays inside the directory.
    """
    parts = path.split("/")
    if path.startswith("/") or any(
        p in {"", ".", ".."} or p.lower() == ".git" for p in parts
    ):
        return "unsafe path"
    if mode == b"120000":
        return "symbolic link"
    if mode not in REGULAR_MODES:
        return "submodule" if mode == b"160000" else f"mode {mode.decode()}"
    if size > MAX_TREE_FILE:
        return f"{size} bytes, over {MAX_TREE_FILE}"
    return None


# --- I/O: git and the GitHub API -------------------------------------------


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"review_inputs: {name} is not set")
    return value


def _git_env() -> dict[str, str]:
    """The environment for git: the token as a one-off header, never persisted."""
    env = dict(os.environ)
    token = os.environ.get("GH_TOKEN")
    if token:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.{server}/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        }
    return env


def git(*args: str) -> bytes:
    """Run git, failing the step with git's own message on any error."""
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        check=False,
        capture_output=True,
        env=_git_env(),
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        sys.exit(f"review_inputs: git {args[0]} failed ({result.returncode}): {stderr}")
    return result.stdout


def git_text(*args: str) -> str:
    return git(*args).decode("utf-8", errors="replace").strip()


def is_ancestor(commit: str, of: str) -> bool:
    """Whether `commit` is reachable from `of` (or is `of`)."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, of],
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        sys.exit(
            f"review_inputs: git merge-base failed ({result.returncode}): {stderr}"
        )
    return result.returncode == 0


class NotFoundError(Exception):
    """The API has no such resource (HTTP 404 or 410)."""


def _gh_json(path: str) -> object:
    """GET one REST resource through `gh`, which reads GH_TOKEN.

    Only a missing resource is the caller's to handle. Any other failure, such
    as a rate limit, fails the step: a review must not go ahead without a
    ticket it could not read.
    """
    result = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github+json", path],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        if "(HTTP 404)" in result.stderr or "(HTTP 410)" in result.stderr:
            raise NotFoundError(path)
        sys.exit(f"review_inputs: gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def api(path: str) -> dict[str, Any]:
    """One REST object."""
    data = _gh_json(path)
    if not isinstance(data, dict):
        sys.exit(f"review_inputs: {path} is not an object")
    return cast("dict[str, Any]", data)


def api_list(path: str) -> list[dict[str, Any]]:
    """Every page of a REST list."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _gh_json(f"{path}?per_page=100&page={page}")
        if not isinstance(batch, list):
            sys.exit(f"review_inputs: {path} is not a list")
        items.extend(cast("list[dict[str, Any]]", batch))
        if len(batch) < 100:
            return items
        page += 1


# --- The files ---------------------------------------------------------------


def write_tree(dest: Path, commit: str) -> tuple[int, list[tuple[str, str]]]:
    """Write `commit`'s tree under `dest` as plain files.

    Returns how many files were written, and each entry left out with why.
    Nothing written is a link, so nothing under `dest` resolves elsewhere.
    """
    skipped: list[tuple[str, str]] = []
    wanted: list[tuple[str, str]] = []
    for entry in git("ls-tree", "-r", "-z", "--long", commit).split(b"\0"):
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        mode, _kind, blob, size = meta.split()
        path = raw_path.decode("utf-8", errors="replace")
        why = tree_skip_reason(mode, int(size) if size.isdigit() else 0, path)
        if why is None:
            wanted.append((path, blob.decode()))
        else:
            skipped.append((path, why))
    contents = blobs([blob for _, blob in wanted])
    written = 0
    for (path, _), content in zip(wanted, contents, strict=True):
        if b"\0" in content[:8000]:
            skipped.append((path, "binary"))
            continue
        target = dest.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written += 1
    return written, sorted(skipped)


def blobs(shas: list[str]) -> list[bytes]:
    """The content of each blob, in order, from one `git cat-file --batch`."""
    if not shas:
        return []
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        input="".join(f"{sha}\n" for sha in shas).encode(),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(
            f"review_inputs: git cat-file failed: {result.stderr.decode(errors='replace')}"
        )
    data, pos, found = result.stdout, 0, []
    for sha in shas:
        end = data.index(b"\n", pos)
        header = data[pos:end].split()  # <sha> <type> <size>
        if len(header) != 3 or header[1] != b"blob":
            sys.exit(f"review_inputs: blob {sha} is missing")
        start = end + 1
        size = int(header[2])
        found.append(data[start : start + size])
        pos = start + size + 1
    return found


# --- Dev merges ----------------------------------------------------------------

# What the review is told the PR is. `dev-merge.md` and `README.md` start with
# `Kind: <one of these>`, and the workflow's prompt branches on it.
KIND_TICKET = "ticket PR"
KIND_DEV_MERGE = "dev-merge PR"
KIND_NOT_DEV_MERGE = "names an epic but is not a dev merge"
KIND_NO_TICKET = "no ticket and no epic"


@dataclass(frozen=True)
class DevMerge:
    """A merge commit of the PR, and the commit of dev it brings in."""

    merge: str
    dev_commit: str


@dataclass(frozen=True)
class MergeEvidence:
    """What git says about a PR's commits, measured against dev and the base."""

    dev_merges: tuple[DevMerge, ...]
    other_merges: tuple[str, ...]
    own_commits: tuple[str, ...]

    @property
    def is_dev_merge(self) -> bool:
        return bool(self.dev_merges)


def merge_evidence(base_sha: str, head_sha: str, dev_sha: str) -> MergeEvidence:
    """Which of the PR's merge commits bring dev in, and its commits not on dev.

    A merge brings dev in when one of its parents (either one: the order
    depends on which branch the merge was made on) is reachable from dev's tip
    and not from the base, so it adds dev commits the epic lacked. The PR's
    own commits are its non-merge commits that are on neither the base nor dev.
    """
    dev_merges: list[DevMerge] = []
    other: list[str] = []
    merges = git_text(
        "rev-list", "--merges", "--reverse", f"{base_sha}..{head_sha}"
    ).split()
    for sha in merges:
        parents = git_text("rev-list", "--parents", "-n", "1", sha).split()[1:]
        brought = [
            p
            for p in parents
            if is_ancestor(p, dev_sha) and not is_ancestor(p, base_sha)
        ]
        if brought:
            dev_merges.extend(DevMerge(sha, p) for p in brought)
        else:
            other.append(sha)
    own = git_text(
        "rev-list", "--no-merges", "--reverse", head_sha, "--not", base_sha, dev_sha
    ).split()
    return MergeEvidence(tuple(dev_merges), tuple(other), tuple(own))


def pr_kind(ticket: int | None, epic_line: int | None, evidence: MergeEvidence) -> str:
    """What the review is to judge the PR as. A `Closes` line always wins."""
    if ticket is not None:
        return KIND_TICKET
    if epic_line is None:
        return KIND_NO_TICKET
    return KIND_DEV_MERGE if evidence.is_dev_merge else KIND_NOT_DEV_MERGE


def _one_line(sha: str) -> str:
    return git_text("log", "-1", "--format=%H %s", sha)


def _kind_text(
    kind: str, evidence: MergeEvidence, base_ref: str, dev_ref: str, epic: int | None
) -> str:
    if kind == KIND_TICKET:
        return (
            "**Not a dev-merge PR.** Its body names a ticket with `Closes #<n>`, "
            "so it is reviewed as a ticket PR. The evidence below is for the record."
        )
    if kind == KIND_DEV_MERGE:
        return (
            f"**This is a dev-merge PR.** Its body names epic #{epic} with "
            f"`Epic: #{epic}`, and git shows it merges `{dev_ref}` into "
            f'`{base_ref}`. Judge it by "Judging a dev-merge PR" in '
            "`docs/agents/code-review.md`: no ticket is expected."
        )
    if kind == KIND_NOT_DEV_MERGE:
        return (
            f"**This is not a dev merge.** Its body names epic #{epic} with "
            f"`Epic: #{epic}` and no ticket, which only a PR that merges "
            f"`{dev_ref}` into the epic may do, but none of its merge commits "
            f"brings in a commit of `{dev_ref}` that `{base_ref}` lacks. "
            "That is a blocking finding: request changes. A ticket PR names its "
            "ticket with `Closes #<ticket>` (`docs/agents/tickets.md`)."
        )
    if evidence.is_dev_merge:
        return (
            "**No ticket, and no epic.** The body names no ticket with "
            "`Closes #<n>` and no epic with `Epic: #<n>`. Git shows it merges "
            f"`{dev_ref}` into `{base_ref}`, so it looks like a dev-merge PR "
            "whose body does not name its epic. That is a blocking finding: "
            "request changes, since the body must say `Epic: #<n>` "
            '(`docs/agents/tickets.md`, "A dev-merge PR").'
        )
    return (
        "**No ticket, and no epic.** The body names no ticket with `Closes #<n>` "
        f"and no epic with `Epic: #<n>`, and git shows no merge of `{dev_ref}`. "
        "That is a blocking finding: request changes. A ticket PR names its "
        "ticket with `Closes #<ticket>` (`docs/agents/tickets.md`)."
    )


def dev_merge_markdown(
    kind: str,
    evidence: MergeEvidence,
    *,
    base_ref: str,
    dev_ref: str,
    dev_sha: str,
    epic: int | None,
) -> str:
    """`dev-merge.md`: the PR's kind, and git's evidence for it."""
    parts = [
        f"Kind: {kind}",
        "",
        "# Dev merge",
        "",
        _kind_text(kind, evidence, base_ref, dev_ref, epic),
        "",
        f"- `{dev_ref}`'s tip now: {dev_sha}",
        f"- Merge commits that bring `{dev_ref}` in: {len(evidence.dev_merges)}",
        f"- Other merge commits: {len(evidence.other_merges)}",
        (
            f"- The PR's own commits, on neither `{base_ref}` nor `{dev_ref}`: "
            f"{len(evidence.own_commits)}"
        ),
        "",
        f"## Merge commits that bring `{dev_ref}` in",
        "",
    ]
    if not evidence.dev_merges:
        parts.append("(none)")
    for dm in evidence.dev_merges:
        behind = git_text("rev-list", "--count", f"{dm.dev_commit}..{dev_sha}")
        parts += [
            f"- {_one_line(dm.merge)}",
            (
                f"  - merges `{dev_ref}` at {_one_line(dm.dev_commit)}, "
                f"{behind} commits behind `{dev_ref}`'s tip now"
            ),
            f"  - its conflict resolutions: `merges/{dm.merge}.patch` (`git show --cc`)",
        ]
    parts += ["", "## Other merge commits", ""]
    if not evidence.other_merges:
        parts.append("(none)")
    parts += [
        f"- {_one_line(sha)}: brings in no commit of `{dev_ref}` that "
        f"`{base_ref}` lacks. `merges/{sha}.patch`"
        for sha in evidence.other_merges
    ]
    parts += [
        "",
        "## The PR's own commits",
        "",
        (
            f"Every non-merge commit of the PR that is on neither `{base_ref}` nor "
            f"`{dev_ref}`, oldest first, with its diff. In a dev-merge PR these are "
            "the fixes the merge needed: judge each one closely."
        ),
        "",
    ]
    if not evidence.own_commits:
        parts.append("(none)")
    for sha in evidence.own_commits:
        show = git(
            "show",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--find-renames",
            "--format=fuller",
            "--stat",
            "--patch",
            sha,
        ).decode("utf-8", errors="replace")
        parts += [
            f"### {_one_line(sha)}",
            "",
            "````diff",
            show.rstrip("\n"),
            "````",
            "",
        ]
    return "\n".join(parts) + "\n"


def _who(item: dict[str, Any]) -> str:
    login = (item.get("user") or {}).get("login", "unknown")
    return f"{login} ({item.get('author_association', 'NONE')})"


def issue_markdown(
    repo: str, kind: str, number: int
) -> tuple[str, dict[str, Any] | None]:
    """The issue as Markdown, and the issue when it was included."""
    title = f"# {kind} #{number}"
    try:
        issue = api(f"repos/{repo}/issues/{number}")
    except NotFoundError:
        return f"{title}\n\nNot found: #{number} is not an issue in {repo}.\n", None
    if "pull_request" in issue:
        return (
            f"{title}\n\nLeft out: #{number} is a pull request, not an issue.\n",
            None,
        )
    if not is_trusted(issue):
        left_out = (
            f"{title}\n\nLeft out: its author, {_who(issue)}, is not the repo's "
            "OWNER, a MEMBER or a COLLABORATOR, so its text is not trusted.\n"
        )
        return left_out, None
    comments = api_list(f"repos/{repo}/issues/{number}/comments")
    kept = [c for c in comments if is_trusted(c)]
    counts = (
        f"- Comments: {len(kept)} shown. {len(comments) - len(kept)} left out, "
        "because their authors are not the repo's OWNER, a MEMBER or a COLLABORATOR."
    )
    parts = [
        f"# {kind} #{number}: {issue.get('title', '')}",
        "",
        f"- Author: {_who(issue)}",
        f"- State: {issue.get('state')}",
        counts,
        "",
        "## Body",
        "",
        issue.get("body") or "(empty)",
        "",
        "## Comments",
        "",
    ]
    if not kept:
        parts.append("(none)")
    for comment in kept:
        parts += [
            "---",
            "",
            f"### Comment by {_who(comment)}, {comment.get('created_at')}",
            "",
            comment.get("body") or "(empty)",
            "",
        ]
    return "\n".join(parts) + "\n", issue


def write_inputs(out: Path) -> None:
    repo = _env("REPO")
    pr_raw = _env("PR")
    base_ref = _env("BASE_REF")
    head_sha = _env("HEAD_SHA")
    if not _DIGITS.fullmatch(pr_raw):
        sys.exit("review_inputs: PR is not a number")
    if not valid_base_ref(base_ref):
        sys.exit("review_inputs: BASE_REF is not an epic/ branch")
    if not _SHA.fullmatch(head_sha):
        sys.exit("review_inputs: HEAD_SHA is not a full commit SHA")
    pr_number = int(pr_raw)

    pr = api(f"repos/{repo}/pulls/{pr_number}")
    if pr["base"]["ref"] != base_ref:
        sys.exit(
            f"review_inputs: the PR now targets {pr['base']['ref']!r}, not the "
            f"{base_ref!r} this run was started for. Not reviewing."
        )
    dev_ref = (pr["base"].get("repo") or {}).get("default_branch") or ""
    if not valid_branch(dev_ref):
        sys.exit(f"review_inputs: the default branch {dev_ref!r} is not a branch name")

    # The PR's head and base, and dev, from the server. The checkout holds
    # dev's full history; a shallow one would hide the merge base.
    shallow = git_text("rev-parse", "--is-shallow-repository") == "true"
    git(
        "fetch",
        "--quiet",
        "--no-tags",
        "--no-recurse-submodules",
        *(["--unshallow"] if shallow else []),
        "origin",
        f"+refs/pull/{pr_number}/head:refs/review/head",
        f"+refs/heads/{base_ref}:refs/review/base",
        f"+refs/heads/{dev_ref}:refs/review/dev",
    )
    fetched_head = git_text("rev-parse", "refs/review/head^{commit}")
    if fetched_head != head_sha:
        # Pushed again since the event: review the event's commit, which is the
        # one the merge job pins. The newer push starts its own run.
        git(
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-recurse-submodules",
            "origin",
            head_sha,
        )
    git("cat-file", "-e", f"{head_sha}^{{commit}}")
    base_sha = git_text("rev-parse", "refs/review/base^{commit}")
    dev_sha = git_text("rev-parse", "refs/review/dev^{commit}")
    merge_base = git_text("merge-base", base_sha, head_sha)

    if out.exists():
        shutil.rmtree(out)
    (out / "merges").mkdir(parents=True)

    # The diff, as GitHub shows a PR's: from the merge base to the head. From
    # git, so no size limit applies.
    diff_args = ("--no-color", "--no-ext-diff", "--no-textconv", "--find-renames")
    diff = git("diff", *diff_args, merge_base, head_sha)
    (out / "diff.patch").write_bytes(diff)
    diff_lines = diff.decode("utf-8", errors="replace").splitlines(keepends=True)
    files = index_diff(diff_lines)
    (out / "diff-index.tsv").write_text(
        "start_line\tline_count\theader\n"
        + "".join(f"{f.start}\t{f.lines}\t{f.header}\n" for f in files),
        encoding="utf-8",
    )
    name_status = git_text(
        "diff", "--name-status", "--find-renames", merge_base, head_sha
    )
    (out / "files.txt").write_text(name_status + "\n", encoding="utf-8")
    written, skipped = write_tree(out / "head", head_sha)
    (out / "head-skipped.txt").write_text(
        "".join(f"{path}\t{why}\n" for path, why in skipped) or "(none)\n",
        encoding="utf-8",
    )

    # Every commit in the PR, and each merge commit's own changes: `--cc` shows
    # what a merge did beyond taking one side or the other, which is where a
    # conflict resolution hides.
    commits = git_text(
        "log", "--reverse", "--format=%H parents: %P%n    %s", f"{base_sha}..{head_sha}"
    )
    (out / "commits.txt").write_text(commits + "\n", encoding="utf-8")
    merges = git_text(
        "rev-list", "--merges", "--reverse", f"{base_sha}..{head_sha}"
    ).split()
    for sha in merges:
        show = git(
            "show", "--cc", "--no-color", "--no-ext-diff", "--format=fuller", sha
        )
        (out / "merges" / f"{sha}.patch").write_bytes(show)
    commit_count = len(git_text("rev-list", f"{base_sha}..{head_sha}").split())

    pr_body = pr.get("body") or ""
    ticket = ticket_number(pr_body)
    epic_line = named_epic(pr_body) if ticket is None else None
    evidence = merge_evidence(base_sha, head_sha, dev_sha)
    kind = pr_kind(ticket, epic_line, evidence)
    epic: int | None = None
    if ticket is None:
        ticket_md = (
            "# Ticket\n\nNone: the PR body names no ticket with `Closes #<n>`."
            + (
                f" It names its epic with `Epic: #{epic_line}`, as a dev-merge PR "
                "does: see `dev-merge.md`.\n"
                if epic_line is not None
                else "\n"
            )
        )
        epic = epic_line
    else:
        ticket_md, ticket_issue = issue_markdown(repo, "Ticket", ticket)
        if ticket_issue is not None:
            epic = epic_number(ticket_issue.get("body") or "")
    if epic is None:
        epic_md = (
            "# Epic\n\nNone: the PR body has no `Epic: #<n>` line, and no "
            "trusted ticket was found, or its body has no `Part of #<n>` line.\n"
        )
    else:
        epic_md, _ = issue_markdown(repo, "Epic", epic)
    (out / "ticket.md").write_text(ticket_md, encoding="utf-8")
    (out / "epic.md").write_text(epic_md, encoding="utf-8")
    (out / "dev-merge.md").write_text(
        dev_merge_markdown(
            kind,
            evidence,
            base_ref=base_ref,
            dev_ref=dev_ref,
            dev_sha=dev_sha,
            epic=epic_line,
        ),
        encoding="utf-8",
    )

    moved = (
        ""
        if fetched_head == head_sha
        else (
            f"\nThe PR's head has moved on to {fetched_head} since this run started; "
            "this review is of the commit above, which is the only one it can merge.\n"
        )
    )
    counted = ""
    if pr.get("changed_files") != len(files):
        counted = (
            f"\nGitHub counts {pr.get('changed_files')} changed files; the diff "
            f"above has {len(files)}. The base may have moved between the two reads.\n"
        )
    (out / "pr.md").write_text(
        "\n".join(
            [
                f"# PR #{pr_number}: {pr.get('title', '')}",
                "",
                f"- Author: {_who(pr)}",
                f"- Base: {base_ref} (tip {base_sha}, merge base {merge_base})",
                f"- Head: {pr['head']['ref']} (reviewed commit {head_sha})",
                f"- Commits: {commit_count}, of which {len(merges)} are merge commits",
                f"- Files changed: {len(files)}",
                moved + counted,
                "## Body",
                "",
                pr_body or "(empty)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (out / "README.md").write_text(
        f"""Kind: {kind}

# The review's inputs for PR #{pr_number}

Written by `.github/scripts/review_inputs.py` before the review started. This
directory and the working directory around it (a checkout of the default
branch, not the PR, with a few config paths at its root restored from the epic)
are everything the review can read.

- `pr.md`: the PR's title, author, base, head and body.
- `dev-merge.md`: what kind of PR this is (the `Kind:` line above), and git's
  evidence for whether it merges `{dev_ref}` into the epic: the merge commits
  that bring `{dev_ref}` in, and the PR's own commits that are not on
  `{dev_ref}`, with their diffs.
- `ticket.md`: the ticket the PR body closes (`Closes #<n>`), with its comments.
  A dev-merge PR has none.
- `epic.md`: the epic the ticket is `Part of`, with its comments. For a
  dev-merge PR, the epic its body names on its `Epic: #<n>` line.
- `diff.patch`: the full diff, from the merge base {merge_base[:12]} to the
  reviewed commit {head_sha[:12]}. {len(files)} files, {len(diff_lines)} lines.
- `diff-index.tsv`: where each file's section of `diff.patch` starts, and how
  many lines it has: read a file's change with offset and limit.
- `files.txt`: each changed file with its status (A, M, D, R).
- `head/`: the whole tree at the reviewed commit ({written} files), for the
  context around a change. Links, submodules, binaries and files over 1 MB are
  left out; `head-skipped.txt` lists them. Nothing under `head/` is run or
  loaded: it is material to read, like the diff.
- `commits.txt`: the PR's {commit_count} commits, oldest first, with parents.
- `merges/`: `git show --cc` of each of the {len(merges)} merge commits.

The ticket and the epic are included only when the repo's OWNER, a MEMBER or a
COLLABORATOR wrote them, with only the comments those people wrote. Text by
anyone else was left out on purpose.
""",
        encoding="utf-8",
    )
    ticket_named = f"#{ticket}" if ticket else "none"
    epic_named = f"#{epic}" if epic else "none"
    sys.stdout.write(
        f"PR #{pr_number}: {len(files)} files, {len(diff_lines)} diff lines, "
        f"{commit_count} commits ({len(merges)} merges, "
        f"{len(evidence.dev_merges)} bringing in {dev_ref}), "
        f"ticket {ticket_named}, epic {epic_named}, kind: {kind}\n"
    )


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: review_inputs.py <output directory>")
    write_inputs(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
