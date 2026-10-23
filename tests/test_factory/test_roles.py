"""
The role table (#218): who does each stage, where, and what they may touch.

`docs/factory/roles.md` states the same table for people. The equality test at
the bottom is what stops the two drifting; the rest pin `roles.py` itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from factory.merge import POLICY
from factory.roles import (
    RADIUS,
    ROLES,
    allowed,
    permits,
    role_for,
    scope,
)
from factory.routing import Stage

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES_MD = REPO_ROOT / "docs" / "factory" / "roles.md"
DESIGN_MD = REPO_ROOT / "docs" / "factory" / "design.md"

TICKET = 218

# --- The table ---------------------------------------------------------------


def test_there_is_one_row_per_role_in_the_documented_order() -> None:
    assert list(ROLES) == [
        "designer",
        "spec-reviewer",
        "planner",
        "builder",
        "documenter",
        "reviewer",
        "orchestrator",
    ]
    assert all(role.name == key for key, role in ROLES.items())


@pytest.mark.parametrize(
    ("name", "stages", "runs_in"),
    [
        ("designer", ("design",), "own-worktree"),
        ("spec-reviewer", ("spec-review",), "snapshot"),
        ("planner", ("build-planning",), "snapshot"),
        ("builder", ("build-implementing",), "worktree"),
        ("documenter", ("document",), "worktree"),
        ("reviewer", ("review",), "snapshot"),
        ("orchestrator", (), "primary"),
    ],
)
def test_each_role_owns_its_stages_and_runs_where_the_design_says(
    name: str, stages: tuple[str, ...], runs_in: str
) -> None:
    assert tuple(str(stage) for stage in ROLES[name].stages) == stages
    assert ROLES[name].runs_in == runs_in


# --- role_for ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "role"),
    [
        (Stage.DESIGN, "designer"),
        (Stage.SPEC_REVIEW, "spec-reviewer"),
        (Stage.BUILD_PLANNING, "planner"),
        (Stage.BUILD_IMPLEMENTING, "builder"),
        (Stage.DOCUMENT, "documenter"),
        (Stage.REVIEW, "reviewer"),
    ],
)
def test_every_v2_stage_with_a_worker_names_its_role(stage: Stage, role: str) -> None:
    found = role_for(stage)
    assert found is not None
    assert found.name == role


@pytest.mark.parametrize(
    "stage",
    [Stage.ACCEPT, Stage.INTEGRATE, Stage.QA, Stage.PLAN, Stage.TEST],
)
def test_a_stage_with_no_worker_has_no_role(stage: Stage) -> None:
    """
    `accept` is the maintainer's and `integrate` the loop's. `qa` has no worker
    until the QA phase, and `plan` and `test` exist only on v1 chains.
    """
    assert role_for(stage) is None


def test_no_stage_belongs_to_two_roles() -> None:
    owned = [stage for role in ROLES.values() for stage in role.stages]
    assert len(owned) == len(set(owned))


# --- Write scopes ------------------------------------------------------------


def test_the_designer_writes_the_intent_the_spec_and_the_answers() -> None:
    assert scope("designer", TICKET) == (
        ".factory/218/intent.md",
        ".factory/218/spec.md",
        ".factory/218/answers.md",
    )


@pytest.mark.parametrize(
    ("name", "artifact"),
    [
        ("spec-reviewer", "spec-review.md"),
        ("planner", "plan.md"),
        ("reviewer", "review.md"),
    ],
)
def test_a_judge_writes_its_one_artifact(name: str, artifact: str) -> None:
    assert scope(name, TICKET) == (f".factory/218/{artifact}",)


def test_the_orchestrator_writes_nothing() -> None:
    assert scope("orchestrator", TICKET) == ()


def test_the_builder_scope_carries_the_radius_marker_unexpanded() -> None:
    """The radius lives in `plan.md`; #163 expands it. `scope` must not guess."""
    patterns = scope("builder", TICKET)
    assert patterns.count(RADIUS) == 1
    assert "tests/**" in patterns
    assert ".factory/218/plan.md" in patterns
    assert ".factory/218/park.md" in patterns
    assert not permits(patterns, "factory/cli.py")


def test_only_the_builder_has_the_radius_marker() -> None:
    assert [name for name in ROLES if RADIUS in scope(name, TICKET)] == ["builder"]


def test_scope_substitutes_the_ticket_number_and_leaves_no_placeholder() -> None:
    for name in ROLES:
        assert not any("<n>" in pattern for pattern in scope(name, TICKET))
        assert not any("<n>" in pattern for pattern in scope(name, 7))
    assert ".factory/7/spec.md" in scope("designer", 7)


@pytest.mark.parametrize(
    "path",
    [
        "docs/factory/design.md",
        "docs/agents/testing.md",
        "AGENTS.md",
        "docs/AGENTS.md",
        "tests/AGENTS.md",
        "maple/AGENTS.md",
        "CONTEXT.md",
        ".factory/218/plan.md",
        ".factory/218/park.md",
    ],
)
def test_the_documenter_may_write_documentation(path: str) -> None:
    assert permits(scope("documenter", TICKET), path)


@pytest.mark.parametrize(
    "path",
    [
        # Every ADR, and ADR 0003's ratchet mechanics (hard stops).
        "docs/adr/0002-held-keys-ledger.md",
        "docs/agents/typing.md",
        # The merge policy's own document (protected).
        "docs/factory/merge-policy.md",
        # `**/AGENTS.md` must not reach a protected package: factory/** is one.
        "factory/AGENTS.md",
        # ... nor `.claude/`, which changes what is enforced.
        ".claude/AGENTS.md",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "factory/cli.py",
        "maple/decision_makers/inventory_manager.py",
        "botting/controller/inputs.py",
        "configs/maps/henesys.json",
        # Not documentation at all.
        "maple/model/minimap.py",
        ".factory/218/spec.md",
        ".factory/219/plan.md",
    ],
)
def test_the_documenter_may_not_write_what_the_merge_policy_protects(
    path: str,
) -> None:
    assert not permits(scope("documenter", TICKET), path)


def test_the_documenter_excludes_every_policy_pattern_taken_from_merge_py() -> None:
    """Read from `POLICY` here too, so the lists can grow without this test."""
    patterns = scope("documenter", TICKET)
    for pattern in (*POLICY.hard_stop_paths, *POLICY.protected_paths):
        assert f"!{pattern}" in patterns, pattern


def test_a_pattern_is_matched_with_full_match_so_double_star_crosses_directories() -> (
    None
):
    assert permits(("docs/**",), "docs/a/b/c.md")
    assert not permits(("docs/**",), "other/docs/c.md")
    assert permits(("**/AGENTS.md",), "AGENTS.md")
    assert permits(("**/AGENTS.md",), "a/b/AGENTS.md")


def test_an_exclusion_wins_wherever_it_stands() -> None:
    assert not permits(("!docs/adr/**", "docs/**"), "docs/adr/x.md")
    assert not permits(("docs/**", "!docs/adr/**"), "docs/adr/x.md")
    assert permits(("docs/**", "!docs/adr/**"), "docs/x.md")


def test_a_marker_never_matches_a_path() -> None:
    assert not permits((RADIUS,), RADIUS)


# --- allowed -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "argv"),
    [
        ("designer", ["spec", "submit"]),
        ("designer", ["--json", "spec", "submit"]),
        ("designer", ["park", "--reason", "x"]),
        ("designer", ["next", "218"]),
        ("planner", ["plan", "check", "218"]),
        ("builder", ["--json", "plan", "check"]),
        ("documenter", ["doc", "check"]),
        ("orchestrator", ["feature", "new", "--issue", "5"]),
        ("orchestrator", ["--json", "status"]),
        ("spec-reviewer", ["park", "--question", "x"]),
    ],
)
def test_a_listed_command_is_allowed_with_or_without_global_options(
    role: str, argv: list[str]
) -> None:
    assert allowed(role, argv)


@pytest.mark.parametrize(
    ("role", "argv"),
    [
        ("designer", ["plan", "check"]),
        ("designer", ["spec"]),
        ("designer", ["spec", "check"]),
        ("reviewer", ["next"]),
        ("reviewer", ["--json", "spec", "submit"]),
        ("builder", ["accept", "218"]),
        ("builder", ["merge", "check", "5"]),
        ("planner", ["doc", "check"]),
        ("orchestrator", ["plan", "check"]),
        ("orchestrator", []),
    ],
)
def test_a_command_not_listed_is_refused(role: str, argv: list[str]) -> None:
    assert not allowed(role, argv)


@pytest.mark.parametrize("role", list(ROLES))
@pytest.mark.parametrize("argv", [["hook", "stop"], ["--json", "hook", "pre-tool-use"]])
def test_hook_is_allowed_for_every_role_because_the_harness_runs_it(
    role: str, argv: list[str]
) -> None:
    assert allowed(role, argv)


def test_a_global_option_cannot_smuggle_a_command_past_the_list() -> None:
    assert not allowed("reviewer", ["--json", "--json", "run"])


# --- roles.md states the same table ------------------------------------------


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, f"roles.md has no '## {heading}' section"
    return match.group(1)


def _spans(cell: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`([^`]+)`", cell))


def _rows(section: str) -> dict[str, list[tuple[str, ...]]]:
    rows: dict[str, list[tuple[str, ...]]] = {}
    for line in section.splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "Role":
            continue
        rows[cells[0].strip("` ")] = [_spans(cell) for cell in cells[1:]]
    return rows


def test_roles_md_states_the_v2_table_and_it_equals_roles_py() -> None:
    rows = _rows(_section(ROLES_MD.read_text(encoding="utf-8"), "The v2 roles"))
    assert list(rows) == list(ROLES)
    for name, role in ROLES.items():
        stages, runs_in, writes, commands = rows[name]
        assert stages == tuple(str(stage) for stage in role.stages), name
        assert runs_in == (role.runs_in,), name
        assert writes == role.writes, name
        assert commands == tuple(" ".join(words) for words in role.commands), name


def test_roles_md_keeps_the_v1_table_under_its_own_heading() -> None:
    text = ROLES_MD.read_text(encoding="utf-8")
    v1 = _section(text, "The v1 roles")
    for name in ("Clerk", "Specifier", "QA Operator", "Documenter", "Integrator"):
        assert f"| {name} |" in v1
    assert "| Clerk |" not in _section(text, "The v2 roles")


# --- design.md and the Supersedes notes (#218) --------------------------------


def _design() -> str:
    return DESIGN_MD.read_text(encoding="utf-8")


def test_design_reverses_r9_and_keeps_the_documenter() -> None:
    row = next(line for line in _design().splitlines() if line.startswith("| R9 |"))
    assert "No Document stage" not in row
    assert "Documenter" in row


def test_design_places_document_after_the_proof_and_before_review() -> None:
    text = _design()
    table = text[text.index("| `build-implementing` |") : text.index("| `qa` |")]
    assert table.index("| `document` |") > table.index("| `build-implementing` |")
    assert table.index("| `document` |") < table.index("| `review` |")
    assert "and `document` (R9)" not in text


def test_design_names_the_documenter_in_roles_artifacts_and_workers() -> None:
    text = _design()
    assert "| documenter |" in text  # section 8's table
    assert "Documenter" in text[text.index("## 6 ") : text.index("## 7 ")]
    assert "`document`" in text[text.index("## 5 ") : text.index("## 6 ")]


def test_design_no_longer_defers_the_document_stage() -> None:
    text = _design()
    deferred = text[text.index("## 11 ") : text.index("## 12 ")]
    assert "Document stage" not in deferred


def test_design_marks_review_staleness_as_settled_by_237_and_lists_237() -> None:
    text = _design()
    artifacts = text[text.index("## 6 ") : text.index("## 7 ")]
    assert "settled by #237" in artifacts
    build_order = text[text.index("## 10 ") : text.index("## 11 ")]
    assert "#237" in build_order


@pytest.mark.parametrize("name", ["stages.md", "roles.md", "artifacts.md"])
def test_the_supersedes_notes_name_237_for_the_routing_rows(name: str) -> None:
    text = (REPO_ROOT / "docs" / "factory" / name).read_text(encoding="utf-8")
    note = text[: text.index("\n\n", text.index("Supersedes") + 200)]
    assert "#237" in note


def test_stages_md_no_longer_says_the_document_stage_is_removed() -> None:
    text = (REPO_ROOT / "docs" / "factory" / "stages.md").read_text(encoding="utf-8")
    assert "removed (ruling R9)" not in text
