"""
The auto-merge policy, exercised without GitHub.

Every condition is tested from constructed facts in which only that condition
fails, so a test going red names exactly one broken rule. The gatherer is tested
against `gh` output recorded from this repository, and the workflow and the
policy document are tested by parsing them: no criterion of #194 rests on
someone reading a file by eye.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from factory.cli import main
from factory.exit_codes import ExitCode
from factory.merge import (
    POLICY,
    CheckRun,
    Condition,
    FactsUnreadable,
    Policy,
    PullRequestFacts,
    TicketFacts,
    check,
    closing_references,
    could_not_verify,
    evaluate,
    verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "merge-policy.yml"
POLICY_DOC = REPO_ROOT / "docs" / "factory" / "merge-policy.md"

BODY = """\
## What this changes

Tidies the factory docs.

Closes #7

## Could not verify

Nothing touches the bot; fully covered offline.

## Handoff

None.
"""

GREEN = tuple(
    CheckRun(
        name=name, status="completed", conclusion="success", app="github-actions", id=i
    )
    for i, name in enumerate(POLICY.required_checks, start=1)
)


def _passing(**changes: object) -> PullRequestFacts:
    """Facts that satisfy every condition, with `changes` applied."""
    facts = PullRequestFacts(
        number=42,
        repo="flawlessna/legends",
        body=BODY,
        # Not `dev`: the `base="dev"` failure cases below must keep meaning
        # "a base that is not the default branch".
        base="trunk",
        default_branch="trunk",
        head_sha="abc123",
        from_fork=False,
        draft=False,
        paths=("docs/factory/stages.md", "tests/test_factory/test_hooks.py"),
        checks=GREEN,
        ticket=TicketFacts(
            number=7,
            is_issue=True,
            is_open=True,
            labels=frozenset({"type:chore", "method:suite", "factory"}),
        ),
    )
    return replace(facts, **changes)


def _ticket(**changes: object) -> TicketFacts:
    ticket = _passing().ticket
    assert ticket is not None
    return replace(ticket, **changes)


def _failed(facts: PullRequestFacts) -> set[Condition]:
    return {failure.condition for failure in evaluate(facts)}


def _failed_under(path: str, policy: Policy) -> set[Condition]:
    return {f.condition for f in evaluate(_passing(paths=(path,)), policy)}


def test_the_passing_facts_pass() -> None:
    """The baseline every other case breaks exactly one thing in."""
    assert evaluate(_passing()) == []
    assert verdict(evaluate(_passing())) == ExitCode.OK


# --- The two refusals the issue names ---------------------------------------


def test_a_diff_touching_botting_is_refused() -> None:
    facts = _passing(paths=("docs/factory/stages.md", "botting/core/engine.py"))
    assert _failed(facts) == {Condition.PATHS_ALLOWED}
    assert verdict(evaluate(facts)) == ExitCode.NEEDS_HUMAN


def test_a_method_live_ticket_is_refused() -> None:
    facts = _passing(ticket=_ticket(labels=frozenset({"type:chore", "method:live"})))
    assert _failed(facts) == {Condition.TICKET_METHOD}
    assert verdict(evaluate(facts)) == ExitCode.NEEDS_HUMAN


# --- One condition at a time -------------------------------------------------

_CHECKS_PENDING = (*GREEN[:-1], replace(GREEN[-1], status="in_progress", conclusion=""))
_CHECKS_RED = (*GREEN[:-1], replace(GREEN[-1], conclusion="failure"))


@pytest.mark.parametrize(
    ("changes", "condition", "code"),
    [
        ({"body": BODY.replace("Closes #7", "")}, Condition.CLOSES_ONE_TICKET, 1),
        (
            {"body": BODY.replace("Closes #7", "Closes #7, fixes #8")},
            Condition.CLOSES_ONE_TICKET,
            1,
        ),
        ({"ticket": _ticket(is_open=False)}, Condition.CLOSES_ONE_TICKET, 1),
        ({"ticket": _ticket(is_issue=False)}, Condition.CLOSES_ONE_TICKET, 1),
        (
            {"ticket": _ticket(labels=frozenset({"type:build", "method:suite"}))},
            Condition.TICKET_TYPE,
            3,
        ),
        (
            {"ticket": _ticket(labels=frozenset({"method:suite"}))},
            Condition.TICKET_TYPE,
            3,
        ),
        (
            {
                "ticket": _ticket(
                    labels=frozenset({"type:chore", "type:build", "method:suite"})
                )
            },
            Condition.TICKET_TYPE,
            3,
        ),
        (
            {"ticket": _ticket(labels=frozenset({"type:refactor", "method:assent"}))},
            Condition.TICKET_METHOD,
            3,
        ),
        (
            {
                "ticket": _ticket(
                    labels=frozenset({"type:chore", "method:suite", "method:both"})
                )
            },
            Condition.TICKET_METHOD,
            3,
        ),
        ({"paths": ("maple/model/x.py",)}, Condition.PATHS_ALLOWED, 3),
        ({"paths": ("docs/adr/0004-new.md",)}, Condition.NO_HARD_STOP, 3),
        ({"paths": ("docs/factory/merge-policy.md",)}, Condition.NOT_SELF_CHANGE, 3),
        ({"paths": ("factory/cli.py",)}, Condition.NOT_SELF_CHANGE, 3),
        ({"checks": GREEN[:-1]}, Condition.CHECKS_GREEN, 3),
        ({"checks": _CHECKS_PENDING}, Condition.CHECKS_GREEN, 1),
        ({"checks": _CHECKS_RED}, Condition.CHECKS_GREEN, 1),
        (
            {"body": BODY.replace("## Could not verify", "## Not verified")},
            Condition.COULD_NOT_VERIFY,
            1,
        ),
        (
            {
                "body": BODY.replace(
                    "Nothing touches the bot; fully covered offline.", "n/a"
                )
            },
            Condition.COULD_NOT_VERIFY,
            1,
        ),
        ({"base": "dev"}, Condition.WORKING_BRANCH, 3),
        ({"base": "main"}, Condition.WORKING_BRANCH, 3),
        ({"from_fork": True}, Condition.SAME_REPOSITORY, 3),
        ({"draft": True}, Condition.NOT_DRAFT, 1),
    ],
)
def test_each_condition_fails_alone_with_its_own_exit_code(
    changes: dict[str, Any], condition: Condition, code: int
) -> None:
    failures = evaluate(_passing(**changes))
    assert {f.condition for f in failures} == {condition}
    assert verdict(failures) == code


def test_every_failing_condition_is_reported_not_only_the_first() -> None:
    facts = _passing(base="dev", draft=True, from_fork=True, paths=("botting/x.py",))
    assert _failed(facts) == {
        Condition.WORKING_BRANCH,
        Condition.NOT_DRAFT,
        Condition.SAME_REPOSITORY,
        Condition.PATHS_ALLOWED,
    }


def test_a_person_beats_the_author_when_both_are_needed() -> None:
    """Fixing the draft flag would not make it mergeable, so it must not say 1."""
    assert verdict(evaluate(_passing(draft=True, base="dev"))) == ExitCode.NEEDS_HUMAN


def test_without_a_single_ticket_the_labels_are_the_author_s_to_fix() -> None:
    facts = _passing(body=BODY.replace("Closes #7", ""), ticket=None)
    assert _failed(facts) == {
        Condition.CLOSES_ONE_TICKET,
        Condition.TICKET_TYPE,
        Condition.TICKET_METHOD,
    }
    assert verdict(evaluate(facts)) == ExitCode.GATE_FAILED


# --- Paths: the allowlist can widen, the hard stops cannot -------------------


def test_the_hard_stop_check_holds_when_the_allowlist_admits_everything() -> None:
    wide = replace(POLICY, allowed_paths=("**",))
    for path in (
        "botting/controller/inputs/held_keys_ledger.py",
        "configs/maps/x.json",
    ):
        failures = evaluate(_passing(paths=(path,)), wide)
        assert {f.condition for f in failures} == {Condition.NO_HARD_STOP}
        assert verdict(failures) == ExitCode.NEEDS_HUMAN


def test_the_self_change_check_holds_when_the_allowlist_admits_everything() -> None:
    wide = replace(POLICY, allowed_paths=("**",))
    for path in (".github/workflows/merge-policy.yml", "factory/merge.py"):
        failures = evaluate(_passing(paths=(path,)), wide)
        assert {f.condition for f in failures} == {Condition.NOT_SELF_CHANGE}


@pytest.mark.parametrize(
    "path",
    [
        "requirements.txt",
        "ml_training/requirements.txt",
        "pyproject.toml",
        ".pre-commit-config.yaml",
        "botting/telemetry.py",
        "maple/decision_makers/inventory_manager.py",
        "maple/model/mechanics/movement_mechanics_v2.py",
    ],
)
def test_each_hard_stop_family_is_caught(path: str) -> None:
    wide = replace(POLICY, allowed_paths=("**",))
    assert Condition.NO_HARD_STOP in _failed_under(path, wide)


@pytest.mark.parametrize(
    "path",
    [
        "factory_evil/x.py",  # a prefix is not a directory
        "Factory/x.py",  # case-sensitive, though the repo is developed on Windows
        "docsx/a.md",
        "tests/test_botting/test_x.py",
    ],
)
def test_globs_are_anchored_and_case_sensitive(path: str) -> None:
    assert Condition.PATHS_ALLOWED in _failed(_passing(paths=(path,)))


def test_additive_event_types_are_not_a_hard_stop() -> None:
    """AGENTS.md lets Event Types be added freely; only the allowlist stops it."""
    assert _failed(_passing(paths=("botting/telemetry_events.py",))) == {
        Condition.PATHS_ALLOWED
    }


# --- Checks: only GitHub Actions, only the latest, only success --------------


def test_a_check_not_posted_by_github_actions_does_not_count() -> None:
    forged = (*GREEN[:-1], replace(GREEN[-1], app="someone-else"))
    failures = evaluate(_passing(checks=forged))
    assert {f.condition for f in failures} == {Condition.CHECKS_GREEN}
    assert verdict(failures) == ExitCode.NEEDS_HUMAN


def test_the_latest_run_of_a_check_is_the_one_that_counts() -> None:
    rerun_red = (*GREEN, replace(GREEN[0], conclusion="failure", id=99))
    assert _failed(_passing(checks=rerun_red)) == {Condition.CHECKS_GREEN}
    rerun_green = (replace(GREEN[0], conclusion="failure", id=0), *GREEN)
    assert _failed(_passing(checks=rerun_green)) == set()


@pytest.mark.parametrize("conclusion", ["neutral", "skipped", "cancelled", ""])
def test_only_success_is_green(conclusion: str) -> None:
    checks = (*GREEN[:-1], replace(GREEN[-1], conclusion=conclusion))
    assert _failed(_passing(checks=checks)) == {Condition.CHECKS_GREEN}


# --- Reading the body --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Closes #7", (("o/r", 7),)),
        ("closes: #7", (("o/r", 7),)),
        ("FIXES #7", (("o/r", 7),)),
        ("fixed #7 and resolved #7", (("o/r", 7),)),
        ("Resolves Other/Repo#7", (("other/repo", 7),)),
        ("Closes https://github.com/O/R/issues/7", (("o/r", 7),)),
        ("Closes #", ()),
        ("Relates to #7", ()),
        ("prefix #7, disclose #8", ()),
        ("<!-- Closes #7 -->", ()),
        ("Closes #7\nCloses #9", (("o/r", 7), ("o/r", 9))),
    ],
)
def test_the_closing_reference_grammar(
    text: str, expected: tuple[tuple[str, int], ...]
) -> None:
    assert closing_references(text, "o/r") == expected


def test_a_reference_to_another_repository_is_refused() -> None:
    body = BODY.replace("Closes #7", "Closes someone/else#7")
    assert _failed(_passing(body=body)) == {Condition.CLOSES_ONE_TICKET}


def test_the_template_s_own_comment_does_not_fill_the_section() -> None:
    body = "## Could not verify\n\n<!--\nREQUIRED. Say what a human must watch.\n-->\n"
    section = could_not_verify(body)
    assert section is not None
    assert Condition.COULD_NOT_VERIFY in _failed(_passing(body="Closes #7\n" + body))


def test_the_section_runs_to_the_next_heading_of_its_level() -> None:
    body = "## Could not verify\n\n### Detail\n\nThe harness.\n\n## Handoff\n\nX\n"
    section = could_not_verify(body)
    assert section is not None
    assert "The harness." in section
    assert "X" not in section


# --- The gatherer, against recorded gh output --------------------------------

#: Shapes recorded from #196 on 2026-10-17, gh 2.98.0.
_VIEW = {
    "number": 42,
    "url": "https://github.com/FlawlessNa/Legends/pull/42",
    "body": BODY,
    "baseRefName": "movements-improvements",
    "headRefOid": "abc123",
    "isCrossRepository": False,
    "isDraft": False,
    "changedFiles": 2,
}
_FILES = [
    {"filename": "docs/factory/stages.md", "previous_filename": None},
    {"filename": "tests/test_factory/test_hooks.py", "previous_filename": None},
]
_ISSUE = {"state": "open", "is_pr": False, "labels": ["type:chore", "method:suite"]}


class FakeGh:
    """Answers `gh` the way it answered for this repository."""

    def __init__(
        self,
        view: dict[str, Any] | None = None,
        files: list[dict[str, Any]] | None = None,
        issue: dict[str, Any] | None = None,
        default_branch: str = "movements-improvements\n",
        repo_fails: bool = False,
    ) -> None:
        self.default_branch = default_branch
        self.repo_fails = repo_fails
        self.view = {**_VIEW, **(view or {})}
        self.files = _FILES if files is None else files
        self.issue = _ISSUE if issue is None else issue
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        self.calls.append(list(args))
        if args[:2] == ["pr", "view"]:
            return json.dumps(self.view)
        endpoint = args[2] if args[1] == "--paginate" else args[1]
        if endpoint == "repos/flawlessna/legends":
            if self.repo_fails:
                raise FactsUnreadable("gh api failed: HTTP 502")
            assert args[2:] == ["--jq", ".default_branch"], args
            return self.default_branch
        if "/files" in endpoint:
            return "".join(json.dumps(f) + "\n" for f in self.files)
        if "/check-runs" in endpoint:
            return "".join(
                json.dumps(
                    {
                        "name": c.name,
                        "status": c.status,
                        "conclusion": c.conclusion,
                        "id": c.id,
                        "app": c.app,
                    }
                )
                + "\n"
                for c in GREEN
            )
        if "/issues/" in endpoint:
            return json.dumps(self.issue)
        raise AssertionError(f"unexpected gh call: {args}")


def test_recorded_output_for_an_eligible_pr_is_mergeable() -> None:
    code, payload = check(42, FakeGh())
    assert (code, payload["mergeable"], payload["failed"]) == (ExitCode.OK, True, [])
    assert payload["head_sha"] == "abc123"


def test_the_file_list_is_paginated_from_the_rest_endpoint() -> None:
    gh = FakeGh()
    check(42, gh)
    files_call = next(c for c in gh.calls if any("/files" in a for a in c))
    assert "--paginate" in files_call


def test_a_rename_is_judged_by_its_old_path_too() -> None:
    files = [
        {"filename": "docs/moved.py", "previous_filename": "botting/core/engine.py"},
        _FILES[1],
    ]
    code, payload = check(42, FakeGh(files=files))
    assert code == ExitCode.NEEDS_HUMAN
    assert [f["condition"] for f in payload["failed"]] == ["paths-allowed"]
    assert "botting/core/engine.py" in payload["failed"][0]["reason"]


def test_a_short_file_list_is_unreadable_not_judged() -> None:
    code, payload = check(42, FakeGh(view={"changedFiles": 3001}))
    assert code == ExitCode.NEEDS_HUMAN
    assert payload["readable"] is False


def test_fork_status_comes_from_the_head_repository() -> None:
    code, payload = check(42, FakeGh(view={"isCrossRepository": True}))
    assert code == ExitCode.NEEDS_HUMAN
    assert [f["condition"] for f in payload["failed"]] == ["same-repository"]


def test_a_pull_request_is_not_a_ticket() -> None:
    code, payload = check(42, FakeGh(issue={**_ISSUE, "is_pr": True}))
    assert code == ExitCode.GATE_FAILED
    assert [f["condition"] for f in payload["failed"]] == ["closes-one-ticket"]


def test_gh_failing_is_unreadable() -> None:
    def broken(args: Sequence[str]) -> str:
        raise FactsUnreadable("gh pr failed: HTTP 502")

    code, payload = check(42, broken)
    assert code == ExitCode.NEEDS_HUMAN
    assert payload == {
        "pr": 42,
        "readable": False,
        "mergeable": False,
        "error": "gh pr failed: HTTP 502",
    }


def test_a_changed_gh_shape_is_unreadable() -> None:
    code, payload = check(42, FakeGh(view={"headRefOid": None, "url": "nonsense"}))
    assert code == ExitCode.NEEDS_HUMAN
    assert payload["readable"] is False


# --- The command -------------------------------------------------------------


def test_merge_check_speaks_json_through_the_dispatcher(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("factory.merge.run_gh", FakeGh(view={"isDraft": True}))
    assert main(["--json", "merge", "check", "42"]) == ExitCode.GATE_FAILED
    payload = json.loads(capsys.readouterr().out)
    assert [f["condition"] for f in payload["failed"]] == ["not-draft"]


@pytest.mark.parametrize("argv", [["merge", "check", "0"], ["merge", "check", "x"]])
def test_a_malformed_pr_number_is_misuse(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == ExitCode.MISUSE


def test_merge_without_an_action_is_misuse() -> None:
    assert main(["merge"]) == ExitCode.MISUSE


# --- The protected set covers what the verdict depends on --------------------


def _factory_imports(module: Path) -> set[str]:
    """The `factory.*` modules one file imports, anywhere in its body."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        found.update(n for n in names if n == "factory" or n.startswith("factory."))
    return found


def _module_file(name: str) -> str:
    """`factory.cli` -> `factory/cli.py`; a package -> its `__init__.py`."""
    relative = name.replace(".", "/")
    if (REPO_ROOT / f"{relative}.py").is_file():
        return f"{relative}.py"
    return f"{relative}/__init__.py"


def test_every_module_the_console_script_imports_is_protected() -> None:
    """
    A PR that changes what the verdict depends on must never merge itself. The
    closure is computed, not listed, so a new import fails here until a person
    adds it to the protected set.
    """
    seen: set[str] = set()
    pending = ["factory.__main__", "factory.cli"]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(_factory_imports(REPO_ROOT / _module_file(name)))
        if "." in name:
            pending.append(name.rsplit(".", 1)[0])  # importing a.b runs a/__init__
    files = sorted(_module_file(name) for name in seen)
    assert "factory/merge.py" in files
    unprotected = [
        f for f in files if Condition.NOT_SELF_CHANGE not in _failed_under(f, POLICY)
    ]
    assert unprotected == []


# --- The workflow, read as data ---------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_the_workflow_triggers_on_exactly_the_specified_events(
    workflow: dict[Any, Any],
) -> None:
    on = _triggers(workflow)
    assert set(on) == {"pull_request_target", "workflow_run", "workflow_dispatch"}
    assert set(on["pull_request_target"]["types"]) == {
        "opened",
        "edited",
        "reopened",
        "synchronize",
        "ready_for_review",
    }
    assert on["workflow_run"] == {"workflows": ["CI"], "types": ["completed"]}


def test_no_run_step_interpolates_an_expression(workflow: dict[Any, Any]) -> None:
    """Event fields reach scripts through env:, never pasted into the shell."""
    for step in _steps(workflow):
        assert "${{" not in step.get("run", ""), step.get("name")


def test_the_workflow_never_checks_out_the_pull_request(
    workflow: dict[Any, Any],
) -> None:
    checkouts = [
        s
        for s in _steps(workflow)
        if str(s.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    options = checkouts[0]["with"]
    assert options["persist-credentials"] is False
    assert "head" not in options["ref"]
    assert "steps.pr.outputs.base" in options["ref"]


def test_permissions_are_top_level_and_minimal(workflow: dict[Any, Any]) -> None:
    assert workflow["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
        "issues": "read",
        "checks": "read",
    }
    for job in workflow["jobs"].values():
        assert "permissions" not in job


def test_the_workflow_merges_only_the_evaluated_commit(
    workflow: dict[Any, Any],
) -> None:
    merges = [s for s in _steps(workflow) if "gh pr merge" in s.get("run", "")]
    assert len(merges) == 1
    step = merges[0]
    assert step["if"] == "steps.verdict.outputs.code == '0'"
    assert '--match-head-commit "$HEAD"' in step["run"]
    assert "baseRefName,headRefOid" in step["run"]
    concurrency = workflow["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    assert "pull_request.number" in concurrency["group"]


def test_the_workflow_carries_no_condition_of_its_own(workflow: dict[Any, Any]) -> None:
    """The policy lives in factory/merge.py; the YAML only runs it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "factory --json merge check" in text
    for word in ("type:", "method:", "botting", "movements-improvements", "isDraft"):
        assert word not in text


def test_unreadable_fails_the_job_and_wait_does_not(workflow: dict[Any, Any]) -> None:
    evaluate_step = next(s for s in _steps(workflow) if s.get("id") == "verdict")
    run = evaluate_step["run"]
    assert re.search(r"\.readable", run)
    assert "exit 1" in run
    assert "set +e" in run


# --- The policy document -----------------------------------------------------


def test_the_document_states_every_condition_and_value() -> None:
    text = POLICY_DOC.read_text(encoding="utf-8")
    for condition in Condition:
        assert f"`{condition}`" in text, condition
    values = [
        POLICY.method,
        POLICY.check_app,
        *POLICY.auto_merge_types,
        *POLICY.allowed_paths,
        *POLICY.hard_stop_paths,
        *POLICY.protected_paths,
        *POLICY.required_checks,
    ]
    for value in values:
        assert f"`{value}`" in text, value


def test_the_factory_readme_links_the_policy() -> None:
    readme = (REPO_ROOT / "docs" / "factory" / "README.md").read_text(encoding="utf-8")
    assert "(merge-policy.md)" in readme


# --- The allowlist must not be able to disable the enforcement -------------


def test_a_pull_request_touching_dot_claude_waits_for_a_human() -> None:
    """
    `.claude/` is the one directory that changes what is enforced.

    Conditions 2 and 3 trust the ticket's labels, and an agent acting through
    the maintainer's credentials can relabel its own ticket `type:chore`. If
    `.claude/**` were allowlisted, such a PR could disable the hooks in
    `.claude/settings.json` and merge itself unreviewed (#202).
    """
    facts = _passing(paths=("docs/factory/stages.md", ".claude/settings.json"))
    assert _failed(facts) == {Condition.PATHS_ALLOWED}
    assert verdict(evaluate(facts)) == ExitCode.NEEDS_HUMAN


@pytest.mark.parametrize(
    "path",
    [".claude/settings.json", ".claude/skills/factory/SKILL.md", ".claude/hooks/x.sh"],
)
def test_no_part_of_dot_claude_is_allowlisted(path: str) -> None:
    """Settings, skills and hooks all decide what an agent is made to do."""
    assert _failed(_passing(paths=(path,))) == {Condition.PATHS_ALLOWED}


def test_an_artifact_only_pull_request_is_not_refused_on_paths() -> None:
    """
    Every factory ticket writes `.factory/<n>/`. Before #202 the allowlist named
    `factory/**`, a different path, so no ticket PR could ever auto-merge --
    the policy could not fire on the work it was built for.
    """
    facts = _passing(paths=(".factory/202/plan.md", ".factory/202/spec.md"))
    assert Condition.PATHS_ALLOWED not in _failed(facts)


def test_widening_the_allowlist_cannot_relax_a_hard_stop() -> None:
    """
    The two lists are checked independently, and that is load-bearing: a PR
    touching an allowlisted path *and* a hard-stop path still waits.
    """
    facts = _passing(paths=(".factory/202/plan.md", "botting/controller/inputs/x.py"))
    assert Condition.PATHS_ALLOWED in _failed(
        facts
    ) or Condition.NO_HARD_STOP in _failed(facts)
    assert verdict(evaluate(facts)) == ExitCode.NEEDS_HUMAN


# --- The protected package, and the default branch (#217) ---------------------


def test_the_protected_set_names_the_factory_package_as_one_path() -> None:
    """Nine module entries could drift from the package; one glob cannot."""
    assert sorted(POLICY.protected_paths) == sorted(
        [
            "factory/**",
            "docs/factory/merge-policy.md",
            "tests/test_factory/test_merge.py",
            ".github/**",
        ]
    )


def test_a_factory_module_the_console_script_does_not_import_is_protected() -> None:
    """A module nothing imports yet is the one a later import quietly joins."""
    assert Condition.NOT_SELF_CHANGE in _failed_under(
        "factory/not_imported_by_anything.py", POLICY
    )


@pytest.mark.parametrize("branch", ["dev", "main", "develop", "trunk"])
def test_the_working_branch_is_whatever_the_default_branch_is(branch: str) -> None:
    facts = _passing(base=branch, default_branch=branch)
    assert evaluate(facts) == []


def test_a_base_other_than_the_default_branch_names_both() -> None:
    failures = evaluate(_passing(base="feature", default_branch="dev"))
    assert [f.condition for f in failures] == [Condition.WORKING_BRANCH]
    assert verdict(failures) == ExitCode.NEEDS_HUMAN
    assert "feature" in failures[0].reason
    assert "dev" in failures[0].reason


def test_the_policy_holds_no_branch_name() -> None:
    assert not hasattr(POLICY, "working_branch")


def test_the_default_branch_is_read_stripped_from_the_repository() -> None:
    gh = FakeGh(default_branch="movements-improvements\n")
    code, payload = check(42, gh)
    assert code == ExitCode.OK
    assert payload["default_branch"] == "movements-improvements"
    assert ["api", "repos/flawlessna/legends", "--jq", ".default_branch"] in gh.calls


def test_an_empty_default_branch_is_unreadable_not_guessed() -> None:
    code, payload = check(42, FakeGh(default_branch="\n"))
    assert code == ExitCode.NEEDS_HUMAN
    assert payload["readable"] is False


def test_the_repository_call_failing_is_unreadable() -> None:
    code, payload = check(42, FakeGh(repo_fails=True))
    assert code == ExitCode.NEEDS_HUMAN
    assert payload["readable"] is False


# --- The document's lists are the policy's lists -----------------------------


def _path_tokens(text: str) -> set[str]:
    """Backticked tokens that are paths: they hold a `/` or start with a dot."""
    tokens = re.findall(r"`([^`]+)`", text)
    return {t for t in tokens if "/" in t or t.startswith(".")}


def test_condition_four_lists_exactly_the_allowed_paths() -> None:
    row = next(
        line
        for line in POLICY_DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| 4 |")
    )
    assert _path_tokens(row) == set(POLICY.allowed_paths)


def test_the_protected_set_section_lists_exactly_the_protected_paths() -> None:
    text = POLICY_DOC.read_text(encoding="utf-8")
    start = text.index("### The protected set")
    section = text[start:].split("\n## ", 1)[0]
    assert _path_tokens(section) == set(POLICY.protected_paths)
