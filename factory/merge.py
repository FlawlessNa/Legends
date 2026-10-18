"""
The auto-merge policy, evaluated.

`docs/factory/merge-policy.md` states the policy; this module holds its values
and is the only thing that decides it. CI runs `factory merge check <pr>` and
merges on exit 0; an agent runs the same command and sees the same answer. No
agent merges, because no agent decides.

Three layers, kept apart so each can be tested without the next:

- `evaluate` is a pure function of `PullRequestFacts`. Every condition lives
  there and nowhere else -- not in the workflow, not in the dispatcher.
- `gather` reads those facts from GitHub through an injected `gh` runner, so it
  is tested against recorded output with no network.
- `check` joins them and returns `(ExitCode, payload)` like every handler.

**The default is to wait.** A fact that cannot be read is never guessed at: it
is `NEEDS_HUMAN`, flagged `readable: false`, and CI fails the job rather than
sitting silently on a broken gatherer.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Final

from factory.exit_codes import ExitCode


@dataclass(frozen=True)
class Policy:
    """
    The dial. Widening any of it is an edit to this file, which the policy
    itself never merges -- so `git log` names who decided.
    """

    #: The one base branch CI may merge into.
    working_branch: str
    #: `auto_merge_types` (#160) at its first notch.
    auto_merge_types: frozenset[str]
    #: The ticket's only permitted `method:` label.
    method: str
    #: Every path in the diff must match one of these.
    allowed_paths: tuple[str, ...]
    #: `AGENTS.md` -> What you may change, as globs. Checked independently of
    #: `allowed_paths`, so widening that can never relax this.
    hard_stop_paths: tuple[str, ...]
    #: The policy and everything its verdict depends on. Never merged by CI.
    protected_paths: tuple[str, ...]
    #: Checks that must be green on the head commit. #151 produces them.
    required_checks: tuple[str, ...]
    #: The only app whose check runs count.
    check_app: str


POLICY: Final = Policy(
    working_branch="movements-improvements",
    auto_merge_types=frozenset({"type:chore", "type:refactor"}),
    method="method:suite",
    allowed_paths=(
        "factory/**",
        "docs/**",
        "tests/test_factory/**",
        # Every factory ticket writes its artifact chain here. Without this the
        # policy can never fire on the work it was built for.
        ".factory/**",
        # NOT `.claude/**`. Conditions 2 and 3 trust the ticket's labels, and an
        # agent acting through the maintainer's credentials can relabel its own
        # ticket `type:chore`. The hooks and permissions that would stop it live
        # in `.claude/`, so allowing it lets a PR disable the gates and merge
        # itself. It is the one directory that changes what is enforced (#202).
    ),
    hard_stop_paths=(
        # Input send path, focus handling, Held-Keys Ledger (ADR 0002).
        "botting/controller/**",
        # Dispatch-time compilation (ADR 0002).
        "maple/model/mechanics/movement_mechanics_v2.py",
        # Telemetry envelope and transport (ADR 0001).
        "botting/__init__.py",
        "botting/logging_config.py",
        "botting/telemetry.py",
        # Anything an ADR decides: the ADRs, and ADR 0003's ratchet mechanics.
        "docs/adr/**",
        "docs/agents/typing.md",
        # Map JSON.
        "configs/maps/**",
        # Pinned dependency versions, hook revisions included.
        "**/requirements*.txt",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        # Parked.
        "maple/decision_makers/inventory_manager.py",
    ),
    protected_paths=(
        "docs/factory/merge-policy.md",
        "tests/test_factory/test_merge.py",
        ".github/**",
        # The console script's transitive import closure, and its entry point.
        # A test computes the closure and fails when a module joins it unlisted.
        "factory/__init__.py",
        "factory/__main__.py",
        "factory/chain.py",
        "factory/cli.py",
        "factory/exit_codes.py",
        "factory/hooks.py",
        "factory/merge.py",
    ),
    required_checks=("suite", "ruff-check", "ruff-format", "pyright"),
    check_app="github-actions",
)


class Condition(StrEnum):
    """Each condition the policy checks. The value is what a report names."""

    CLOSES_ONE_TICKET = "closes-one-ticket"
    TICKET_TYPE = "ticket-type"
    TICKET_METHOD = "ticket-method"
    PATHS_ALLOWED = "paths-allowed"
    NO_HARD_STOP = "no-hard-stop"
    CHECKS_GREEN = "checks-green"
    COULD_NOT_VERIFY = "could-not-verify"
    WORKING_BRANCH = "working-branch"
    NOT_SELF_CHANGE = "not-self-change"
    SAME_REPOSITORY = "same-repository"
    NOT_DRAFT = "not-draft"


@dataclass(frozen=True)
class CheckRun:
    """One check run on the head commit."""

    name: str
    status: str
    conclusion: str
    app: str
    id: int


@dataclass(frozen=True)
class TicketFacts:
    """The one ticket a PR closes, as GitHub reports it."""

    number: int
    is_issue: bool
    is_open: bool
    labels: frozenset[str]


@dataclass(frozen=True)
class PullRequestFacts:
    """Everything `evaluate` reads. Nothing else reaches the verdict."""

    number: int
    #: `owner/name`, lower-cased.
    repo: str
    body: str
    base: str
    head_sha: str
    from_fork: bool
    draft: bool
    #: Every path the diff touches, the old path of a rename included.
    paths: tuple[str, ...]
    checks: tuple[CheckRun, ...]
    #: Present only when the body references exactly one ticket in this repo.
    ticket: TicketFacts | None


@dataclass(frozen=True)
class Failure:
    """A condition that did not hold, and whether a person must settle it."""

    condition: Condition
    reason: str
    needs_human: bool


# --- Reading the PR body -----------------------------------------------------

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: A closing keyword, then `#n`, `owner/repo#n`, or an issue URL.
_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+"
    r"(?:"
    r"https://github\.com/(?P<url_repo>[\w.-]+/[\w.-]+)/issues/(?P<url_n>\d+)"
    r"|(?P<repo>[\w.-]+/[\w.-]+)?#(?P<n>\d+)"
    r")",
    re.IGNORECASE,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

#: Section bodies that say nothing while looking filled in.
_PLACEHOLDERS: Final = frozenset({"n/a", "na", "none", "tbd", "-"})


def strip_comments(text: str) -> str:
    """The text without HTML comments, so a template's own prose never counts."""
    return _COMMENT.sub("", text)


def closing_references(body: str, repo: str) -> tuple[tuple[str, int], ...]:
    """
    The distinct `(owner/name, number)` pairs the body says it closes.

    A bare `#n` belongs to `repo`. Order is first appearance.
    """
    found: dict[tuple[str, int], None] = {}
    for match in _CLOSING.finditer(strip_comments(body)):
        if match.group("url_n"):
            ref = (match.group("url_repo").lower(), int(match.group("url_n")))
        else:
            ref = ((match.group("repo") or repo).lower(), int(match.group("n")))
        found[ref] = None
    return tuple(found)


def could_not_verify(body: str) -> str | None:
    """
    The "Could not verify" section's text, or None when there is no such
    heading. Runs to the next heading of the same or a higher level.
    """
    lines = strip_comments(body).splitlines()
    for index, line in enumerate(lines):
        heading = _HEADING.match(line)
        if not heading or not heading.group(2).lower().startswith("could not verify"):
            continue
        level = len(heading.group(1))
        section: list[str] = []
        for following in lines[index + 1 :]:
            nested = _HEADING.match(following)
            if nested and len(nested.group(1)) <= level:
                break
            section.append(following)
        return "\n".join(section)
    return None


def _says_something(section: str) -> bool:
    """Whether a section holds more than whitespace or a placeholder."""
    text = section.strip()
    return bool(re.search(r"\w", text)) and text.lower() not in _PLACEHOLDERS


# --- The evaluation ----------------------------------------------------------


def _matching(paths: Iterable[str], globs: Sequence[str]) -> list[str]:
    """The paths matching any glob: anchored, case-sensitive, `*` in one segment."""
    return [p for p in paths if any(PurePosixPath(p).full_match(g) for g in globs)]


def _check_closing(facts: PullRequestFacts) -> Failure | None:
    refs = closing_references(facts.body, facts.repo)
    if len(refs) != 1:
        found = ", ".join(f"{r}#{n}" for r, n in refs) or "none"
        return Failure(
            Condition.CLOSES_ONE_TICKET,
            f"The PR must close exactly one ticket; it closes {found}.",
            needs_human=False,
        )
    repo, number = refs[0]
    if repo != facts.repo:
        return Failure(
            Condition.CLOSES_ONE_TICKET,
            f"It closes {repo}#{number}, which is not in {facts.repo}.",
            needs_human=False,
        )
    ticket = facts.ticket
    if ticket is None or not ticket.is_issue or not ticket.is_open:
        return Failure(
            Condition.CLOSES_ONE_TICKET,
            f"#{number} is not an open issue in {facts.repo}.",
            needs_human=False,
        )
    return None


def _check_type(facts: PullRequestFacts, policy: Policy) -> Failure | None:
    if facts.ticket is None:
        return Failure(
            Condition.TICKET_TYPE,
            "No single ticket to read a type label from.",
            needs_human=False,
        )
    types = sorted(label for label in facts.ticket.labels if label.startswith("type:"))
    if types and all(label in policy.auto_merge_types for label in types):
        return None
    allowed = ", ".join(sorted(policy.auto_merge_types))
    return Failure(
        Condition.TICKET_TYPE,
        f"Ticket type {types or 'missing'}; every type label must be one of {allowed}.",
        needs_human=True,
    )


def _check_method(facts: PullRequestFacts, policy: Policy) -> Failure | None:
    if facts.ticket is None:
        return Failure(
            Condition.TICKET_METHOD,
            "No single ticket to read a method label from.",
            needs_human=False,
        )
    methods = sorted(m for m in facts.ticket.labels if m.startswith("method:"))
    if methods == [policy.method]:
        return None
    return Failure(
        Condition.TICKET_METHOD,
        f"Ticket method {methods or 'missing'}; it must be exactly {policy.method}.",
        needs_human=True,
    )


def _check_paths(facts: PullRequestFacts, policy: Policy) -> list[Failure]:
    failures: list[Failure] = []
    allowed = set(_matching(facts.paths, policy.allowed_paths))
    outside = [p for p in facts.paths if p not in allowed]
    if outside:
        failures.append(
            Failure(
                Condition.PATHS_ALLOWED,
                f"Outside the allowlist: {', '.join(outside)}.",
                needs_human=True,
            )
        )
    hard_stop = _matching(facts.paths, policy.hard_stop_paths)
    if hard_stop:
        failures.append(
            Failure(
                Condition.NO_HARD_STOP,
                f"On the AGENTS.md hard-stop list: {', '.join(hard_stop)}.",
                needs_human=True,
            )
        )
    protected = _matching(facts.paths, policy.protected_paths)
    if protected:
        failures.append(
            Failure(
                Condition.NOT_SELF_CHANGE,
                f"Changes the merge policy itself: {', '.join(protected)}.",
                needs_human=True,
            )
        )
    return failures


def _check_checks(facts: PullRequestFacts, policy: Policy) -> Failure | None:
    latest: dict[str, CheckRun] = {}
    for run in facts.checks:
        if run.app != policy.check_app:
            continue
        if run.name not in latest or run.id > latest[run.name].id:
            latest[run.name] = run
    missing = [name for name in policy.required_checks if name not in latest]
    not_green = [
        f"{name} ({latest[name].conclusion or latest[name].status})"
        for name in policy.required_checks
        if name in latest
        and (latest[name].status != "completed" or latest[name].conclusion != "success")
    ]
    if not missing and not not_green:
        return None
    parts = []
    if missing:
        parts.append(f"never reported: {', '.join(missing)}")
    if not_green:
        parts.append(f"not green: {', '.join(not_green)}")
    return Failure(
        Condition.CHECKS_GREEN,
        f"Required checks {'; '.join(parts)}.",
        needs_human=bool(missing),
    )


def evaluate(facts: PullRequestFacts, policy: Policy = POLICY) -> list[Failure]:
    """Every condition that does not hold. Empty means CI may merge."""
    failures: list[Failure] = []

    def add(failure: Failure | None) -> None:
        if failure is not None:
            failures.append(failure)

    add(_check_closing(facts))
    add(_check_type(facts, policy))
    add(_check_method(facts, policy))
    failures.extend(_check_paths(facts, policy))
    add(_check_checks(facts, policy))

    section = could_not_verify(facts.body)
    if section is None or not _says_something(section):
        add(
            Failure(
                Condition.COULD_NOT_VERIFY,
                "The PR body's 'Could not verify' section is "
                + ("missing." if section is None else "empty."),
                needs_human=False,
            )
        )
    if facts.base != policy.working_branch:
        add(
            Failure(
                Condition.WORKING_BRANCH,
                f"Base is {facts.base}; only {policy.working_branch} is merged by CI.",
                needs_human=True,
            )
        )
    if facts.from_fork:
        add(
            Failure(
                Condition.SAME_REPOSITORY,
                "The head branch lives in a fork.",
                needs_human=True,
            )
        )
    if facts.draft:
        add(Failure(Condition.NOT_DRAFT, "The PR is a draft.", needs_human=False))
    return failures


def verdict(failures: Sequence[Failure]) -> ExitCode:
    """0 to merge; 3 when a person is needed at all; 1 when only the author is."""
    if not failures:
        return ExitCode.OK
    if any(f.needs_human for f in failures):
        return ExitCode.NEEDS_HUMAN
    return ExitCode.GATE_FAILED


# --- Gathering the facts -----------------------------------------------------

#: Runs `gh` with these arguments and returns stdout, or raises `FactsUnreadable`.
Runner = Callable[[Sequence[str]], str]

_PR_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/pull/\d+$")


class FactsUnreadable(Exception):
    """GitHub could not be read, or answered in a shape that cannot be trusted."""


def run_gh(args: Sequence[str]) -> str:
    """The real runner: `gh` on PATH, authenticated by its own configuration."""
    try:
        done = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FactsUnreadable(f"gh could not run: {error}") from error
    if done.returncode != 0:
        raise FactsUnreadable(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()}")
    return done.stdout


def _json_lines(text: str) -> list[dict[str, Any]]:
    """One JSON object per line, which is how `gh --jq` prints objects."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            loaded = json.loads(line)
            if not isinstance(loaded, dict):
                raise FactsUnreadable(f"Expected an object per line, got: {line}")
            out.append(loaded)
    return out


def gather(pr: int, gh: Runner) -> PullRequestFacts:
    """
    Read one PR's facts from GitHub.

    The file list comes from the REST endpoint, because GraphQL's `files` stops
    at 100 and does not report the old path of a rename. A list shorter than the
    PR's own changed-file count is refused rather than judged.
    """
    try:
        view = json.loads(
            gh(
                [
                    "pr",
                    "view",
                    str(pr),
                    "--json",
                    (
                        "number,url,body,baseRefName,headRefOid,"
                        "isCrossRepository,isDraft,changedFiles"
                    ),
                ]
            )
        )
        url = _PR_URL.match(view["url"])
        if url is None:
            raise FactsUnreadable(f"Unrecognised PR url: {view['url']}")
        repo = url.group(1).lower()
        head_sha = str(view["headRefOid"])
        body = str(view.get("body") or "")

        files = _json_lines(
            gh(
                [
                    "api",
                    "--paginate",
                    f"repos/{repo}/pulls/{pr}/files?per_page=100",
                    "--jq",
                    ".[] | {filename, previous_filename}",
                ]
            )
        )
        if len(files) != int(view["changedFiles"]):
            raise FactsUnreadable(
                f"Read {len(files)} files of {view['changedFiles']}; "
                "a partial list cannot be judged."
            )
        paths: dict[str, None] = {}
        for entry in files:
            paths[str(entry["filename"])] = None
            if entry.get("previous_filename"):
                paths[str(entry["previous_filename"])] = None

        checks = tuple(
            CheckRun(
                name=str(run["name"]),
                status=str(run["status"]),
                conclusion=str(run.get("conclusion") or ""),
                app=str(run.get("app") or ""),
                id=int(run["id"]),
            )
            for run in _json_lines(
                gh(
                    [
                        "api",
                        "--paginate",
                        f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100",
                        "--jq",
                        ".check_runs[] | {name, status, conclusion, id, app: .app.slug}",
                    ]
                )
            )
        )

        ticket = None
        refs = closing_references(body, repo)
        if len(refs) == 1 and refs[0][0] == repo:
            issue = json.loads(
                gh(
                    [
                        "api",
                        f"repos/{repo}/issues/{refs[0][1]}",
                        "--jq",
                        '{state, is_pr: has("pull_request"), labels: [.labels[].name]}',
                    ]
                )
            )
            ticket = TicketFacts(
                number=refs[0][1],
                is_issue=not issue["is_pr"],
                is_open=issue["state"] == "open",
                labels=frozenset(str(label) for label in issue["labels"]),
            )
    except (KeyError, TypeError, ValueError) as error:
        raise FactsUnreadable(f"Unexpected shape from gh: {error!r}") from error

    return PullRequestFacts(
        number=int(view["number"]),
        repo=repo,
        body=body,
        base=str(view["baseRefName"]),
        head_sha=head_sha,
        from_fork=bool(view["isCrossRepository"]),
        draft=bool(view["isDraft"]),
        paths=tuple(paths),
        checks=checks,
        ticket=ticket,
    )


def check(pr: int, gh: Runner | None = None) -> tuple[ExitCode, dict[str, Any]]:
    """
    The whole evaluation for one PR, as a handler result.

    `readable: false` means GitHub could not be read. It returns `NEEDS_HUMAN`,
    so nothing merges; CI additionally fails the job, so it is seen.
    """
    try:
        facts = gather(pr, gh or run_gh)
    except FactsUnreadable as error:
        return ExitCode.NEEDS_HUMAN, {
            "pr": pr,
            "readable": False,
            "mergeable": False,
            "error": str(error),
        }
    failures = evaluate(facts)
    code = verdict(failures)
    return code, {
        "pr": pr,
        "readable": True,
        "mergeable": code is ExitCode.OK,
        "base": facts.base,
        "head_sha": facts.head_sha,
        "ticket": facts.ticket.number if facts.ticket else None,
        "failed": [
            {
                "condition": str(f.condition),
                "needs_human": f.needs_human,
                "reason": f.reason,
            }
            for f in failures
        ],
    }
