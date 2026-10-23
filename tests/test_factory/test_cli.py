"""The dispatcher's contract: exit codes, and the two output forms."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from factory import __version__
from factory.cli import (
    COMMANDS,
    _stop_everywhere,
    _written_path,
    build_parser,
    ticket_worktrees,
)
from factory.cli import (
    main as main_cli,
)
from factory.exit_codes import ExitCode
from factory.models import TABLE_PATH

from .test_hooks import _linked, _primary


def test_the_exit_codes_are_the_documented_contract() -> None:
    """The numbers are the interface; hooks and CI branch on them."""
    assert (ExitCode.OK, ExitCode.GATE_FAILED) == (0, 1)
    assert (ExitCode.MISUSE, ExitCode.NEEDS_HUMAN) == (2, 3)


def test_misuse_shares_argparse_s_own_failure_code() -> None:
    """A bad invocation and a refused one report the same thing to the caller."""
    with pytest.raises(SystemExit) as caught:
        main_cli(["no-such-command"])
    assert caught.value.code == ExitCode.MISUSE


def test_no_command_is_misuse_not_success() -> None:
    """A bare `factory` has done nothing, so it must not look like it succeeded."""
    assert main_cli([]) == ExitCode.MISUSE


def test_version_reports_the_factory_s_own_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main_cli(["version"]) == ExitCode.OK
    assert capsys.readouterr().out.strip() == f"version: {__version__}"


def test_json_renders_the_same_payload_as_one_object(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every command speaks both forms, so an agent never parses prose."""
    assert main_cli(["--json", "version"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out) == {"version": __version__}


def test_every_registered_command_is_reachable_through_the_parser() -> None:
    """The registry is the only place a command is declared; nothing drifts."""
    parser = build_parser()
    for name in COMMANDS:
        assert parser.parse_args([name]).command == name


# --- `factory model` ---------------------------------------------------------
#
# The exit codes are the contract the Foreman branches on, so they are tested
# through `main` rather than through the resolver: the resolver raising the
# right exception is useless if the dispatcher maps it to the wrong number.


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo root with the real table copied in, since `_model` reads cwd."""
    (tmp_path / "configs").mkdir()
    real = Path(__file__).resolve().parents[2] / TABLE_PATH
    (tmp_path / TABLE_PATH).write_text(real.read_text(encoding="utf-8"), "utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_model_answers_for_a_stage_asked_directly(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main_cli(["--json", "model", "--stage", "design"]) == ExitCode.OK
    assert _payload(capsys)["model"] == "opus"


def test_model_names_the_rule_that_fired(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without this a human cannot ask why a stage got the model it got."""
    assert main_cli(["--json", "model", "--stage", "qa"]) == ExitCode.OK
    payload = _payload(capsys)
    assert payload["rule"] == "stage table: qa"
    assert payload["record"] == "model: sonnet  # tier=standard, rule=stage table: qa"


def test_model_answers_integrate_with_no_model_at_exit_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    A definite "nobody runs this" is an answer. Exiting non-zero would force
    the Foreman to special-case `integrate` before asking about it.
    """
    assert main_cli(["--json", "model", "--stage", "integrate"]) == ExitCode.OK
    assert _payload(capsys)["model"] is None


def test_an_unknown_stage_is_misuse(repo: Path) -> None:
    """`maintain` is the real case: in `stages.md`, in no enum, owned by no role."""
    assert main_cli(["model", "--stage", "maintain"]) == ExitCode.MISUSE


def test_no_ticket_and_no_stage_is_misuse(repo: Path) -> None:
    """There is no stage to answer about; guessing one would be worse."""
    assert main_cli(["model"]) == ExitCode.MISUSE


def test_a_broken_table_needs_a_human_not_a_misuse(repo: Path) -> None:
    """
    The distinction the Foreman branches on: MISUSE means "I asked wrongly",
    and its documented remedy -- re-read `factory next` -- is useless advice
    for a corrupt config file.
    """
    (repo / TABLE_PATH).write_text('unavailable = ["fabel"]\n', encoding="utf-8")
    assert main_cli(["model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN


def test_a_missing_table_needs_a_human(repo: Path) -> None:
    (repo / TABLE_PATH).unlink()
    assert main_cli(["model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN


def test_no_error_path_ever_reports_a_model(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A silent fallback to the strong model turns a typo into a bill."""
    (repo / TABLE_PATH).write_text("tiers = 3\n", encoding="utf-8")
    assert main_cli(["--json", "model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN
    assert "model" not in _payload(capsys)


def test_the_ticket_form_computes_the_stage_from_the_chain(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`factory model <n>` and `factory next <n>` must agree on the stage."""
    chain = repo / ".factory" / "7"
    chain.mkdir(parents=True)
    (chain / "intent.md").write_text(
        "---\nticket: 7\naccepted_by: nassim\n---\n", encoding="utf-8"
    )
    assert main_cli(["--json", "model", "7"]) == ExitCode.OK
    payload = _payload(capsys)
    assert payload["stage"] == "design"
    assert payload["model"] == "opus"


def test_a_blocked_chain_needs_a_human_and_says_why(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    An inconsistent chain is not a model question. The Foreman must report the
    chain's reason, not a model's.
    """
    chain = repo / ".factory" / "7"
    chain.mkdir(parents=True)
    (chain / "plan.md").write_text("---\nticket: 7\n---\n", encoding="utf-8")
    assert main_cli(["--json", "model", "7"]) == ExitCode.NEEDS_HUMAN
    assert _payload(capsys)["blocked_by"]


# --- The hook's view of a path, and of the worktrees (#206) ------------------


def _wt(root: Path, branch: str, ticket: int | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    if ticket is not None:
        (root / ".factory" / str(ticket)).mkdir(parents=True, exist_ok=True)
    return root


def test_a_relative_target_is_anchored_on_the_event_s_cwd(tmp_path: Path) -> None:
    """
    `PreToolUse` fires on the model's raw arguments, before the tool validates
    them, so a relative path is reachable. Resolved later it lands against the
    hook's own cwd -- the session's worktree, not the target's -- and the gate
    answers about the wrong ticket. That is the bug surviving its own fix.
    """
    target = _written_path(
        {"tool_input": {"file_path": "factory/cli.py"}, "cwd": str(tmp_path / "other")}
    )
    assert target == tmp_path / "other" / "factory" / "cli.py"


def test_an_absolute_target_is_left_alone(tmp_path: Path) -> None:
    absolute = tmp_path / "a" / "factory" / "cli.py"
    assert _written_path({"tool_input": {"file_path": str(absolute)}}) == absolute


def test_a_relative_target_falls_back_to_the_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The event may not carry `cwd`; the process cwd is the best guess left."""
    monkeypatch.chdir(tmp_path)
    assert _written_path({"tool_input": {"file_path": "x.py"}}) == tmp_path / "x.py"


def test_a_tool_that_writes_nothing_has_no_target() -> None:
    assert _written_path({"tool_input": {"pattern": "foo"}}) is None
    assert _written_path({}) is None


def test_every_ticket_worktree_is_found_from_the_main_checkout(tmp_path: Path) -> None:
    """
    The Stop gate judged only the session's worktree, which in the workflow
    this factory was built under is the main checkout on a non-ticket branch --
    so the proof gate returned indifference on every turn, forever.
    """
    main = _wt(tmp_path / "main", "movements-improvements")
    worktrees = main / ".git" / "worktrees"
    for name, branch in (("a", "issue/1-x"), ("b", "issue/2-x"), ("c", "dev")):
        linked = _wt(tmp_path / name, branch)
        (worktrees / name).mkdir(parents=True)
        (worktrees / name / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")
        (worktrees / name / "HEAD").write_text(
            f"ref: refs/heads/{branch}\n", encoding="utf-8"
        )

    found = ticket_worktrees(main)
    assert {root.name for root in found} == {"a", "b"}, "c is not a ticket branch"


def test_the_session_s_own_worktree_is_included_when_it_qualifies(
    tmp_path: Path,
) -> None:
    """A session inside its own ticket worktree is judged exactly as before."""
    own = _wt(tmp_path / "own", "issue/9-x", 9)
    assert ticket_worktrees(own) == (own,)


def test_a_directory_that_is_not_a_repository_has_no_worktrees(tmp_path: Path) -> None:
    assert ticket_worktrees(tmp_path) == ()


def test_the_stop_gate_refuses_for_a_worktree_the_session_is_not_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The gate this ticket resurrects.

    The session is in the main checkout on a non-ticket branch; a ticket
    worktree has source changed and no proof recorded. Before #206 the turn
    ended cleanly, because the only worktree consulted was the one with nothing
    to say.
    """
    main = _wt(tmp_path / "main", "movements-improvements")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: null\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")

    monkeypatch.setattr("factory.cli._source_changed", lambda root: root == linked)
    decision = _stop_everywhere(main)
    assert not decision.allowed
    assert "5" in decision.reason


def test_the_stop_gate_is_quiet_when_every_worktree_has_its_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = _wt(tmp_path / "main", "movements-improvements")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: pass\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")

    monkeypatch.setattr("factory.cli._source_changed", lambda root: True)
    assert _stop_everywhere(main).allowed


def test_the_stop_gate_runs_git_in_each_worktree_not_in_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git status` in the session's root cannot see another worktree's changes."""
    main = _wt(tmp_path / "main", "movements-improvements")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")

    asked: list[Path] = []
    monkeypatch.setattr(
        "factory.cli._source_changed", lambda root: asked.append(root) or False
    )
    _stop_everywhere(main)
    assert asked == [linked]


def test_the_stop_hook_is_wired_to_the_fold_not_to_one_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Through `main`, because the fold being correct is worth nothing if the hook
    does not call it.

    Written after reverting the wiring and watching the three `_stop_everywhere`
    tests all stay green: they exercised the fold directly and pinned nothing
    about the hook. A gate is only as enforced as its call site.
    """
    main = _wt(tmp_path / "main", "movements-improvements")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: null\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")

    monkeypatch.chdir(main)
    monkeypatch.setattr("factory.cli._source_changed", lambda root: root == linked)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))

    assert main_cli(["hook", "stop"]) == ExitCode.OK
    answer = json.loads(capsys.readouterr().out)
    assert answer["decision"] == "block"
    assert "5" in answer["reason"]


def test_the_pre_tool_use_hook_judges_the_target_s_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same, for the write gate: the call site must pass the target."""
    main = _wt(tmp_path / "main", "movements-improvements")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    monkeypatch.chdir(main)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {"tool_input": {"file_path": str(linked / "botting" / "core.py")}}
            )
        ),
    )

    assert main_cli(["hook", "pre-tool-use"]) == ExitCode.OK
    answer = json.loads(capsys.readouterr().out)
    specific = answer["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "Ticket 5" in specific["permissionDecisionReason"]


def test_the_pre_tool_use_hook_still_reaches_the_session_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    The session row's regression detector, rebuilt for #209.

    It used to write the trunk from a ticket worktree. #209 refuses that
    outright, so the detector had to move to the one target the session row
    still answers for: a **linked, non-ticket** worktree in the same
    repository. Dropping `session=` at the call site must still be noticed.
    """
    main = _primary(tmp_path / "main", "dev")
    builder = _linked(main, tmp_path / "wt", "issue/5-x", 5)
    sibling = _linked(main, tmp_path / "other", "scratch-branch")
    monkeypatch.chdir(builder)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {"tool_input": {"file_path": str(sibling / "botting" / "core.py")}}
            )
        ),
    )

    assert main_cli(["hook", "pre-tool-use"]) == ExitCode.OK
    specific = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "Ticket 5" in specific["permissionDecisionReason"]


def _hook_answer(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """The hook's JSON, after asserting there is some: no answer is its own failure."""
    out = capsys.readouterr().out
    assert out.strip(), "the hook made no decision"
    return json.loads(out)


def test_the_pre_tool_use_hook_takes_the_session_from_the_event_s_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    The event names the session's directory; the process cwd is only a guess (#216).

    Here the process runs somewhere unrelated, and the event says the session
    is a builder worktree. Judged from the process cwd, the session is nobody
    and the write is waved through.
    """
    main = _primary(tmp_path / "main", "dev")
    builder = _linked(main, tmp_path / "wt", "issue/5-x", 5)
    sibling = _linked(main, tmp_path / "other", "scratch-branch")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "cwd": str(builder),
                    "tool_input": {"file_path": str(sibling / "botting" / "core.py")},
                }
            )
        ),
    )

    assert main_cli(["hook", "pre-tool-use"]) == ExitCode.OK
    specific = _hook_answer(capsys)["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "Ticket 5" in specific["permissionDecisionReason"]


def test_the_stop_hook_takes_the_session_from_the_event_s_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same for Stop: from an unrelated directory, no worktree was ever found."""
    main = _wt(tmp_path / "main", "dev")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: null\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr("factory.cli._source_changed", lambda root: root == linked)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(main)})))

    assert main_cli(["hook", "stop"]) == ExitCode.OK
    answer = _hook_answer(capsys)
    assert answer["decision"] == "block"
    assert "5" in answer["reason"]


def test_a_cwd_naming_no_directory_falls_back_to_the_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale or malformed `cwd` must not move the session somewhere imaginary."""
    main = _wt(tmp_path / "main", "dev")
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: null\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")

    monkeypatch.chdir(main)
    monkeypatch.setattr("factory.cli._source_changed", lambda root: root == linked)
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"cwd": str(tmp_path / "gone")}))
    )

    assert main_cli(["hook", "stop"]) == ExitCode.OK
    assert _hook_answer(capsys)["decision"] == "block"


class _Terminal(io.StringIO):
    """A stdin that is a terminal, and fails the test if anything reads it."""

    def isatty(self) -> bool:
        return True

    def read(self, size: int | None = -1) -> str:
        raise AssertionError("the hook read from a terminal and would hang")


def test_a_hook_run_by_hand_in_a_terminal_does_not_read_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    `bash .claude/hooks/factory-hook.sh session-start` is how a person checks the
    gates are alive (SKILL.md). Every event reads its JSON now, so a terminal on
    stdin would wait forever for input nobody is going to type.
    """
    monkeypatch.chdir(_wt(tmp_path / "main", "dev"))
    monkeypatch.setattr("sys.stdin", _Terminal())

    assert main_cli(["hook", "session-start"]) == ExitCode.OK
    assert "factory gates: LIVE" in capsys.readouterr().out


def test_a_cwd_inside_a_worktree_is_judged_from_the_worktree_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    A session in a subdirectory is still that worktree's session.

    Taken raw, a `cwd` of `<main>/botting` was not a repository root, so no
    ticket worktree was found and the Stop gate said nothing (review of #216).
    """
    main = _wt(tmp_path / "main", "dev")
    (main / "botting").mkdir()
    linked = _wt(tmp_path / "wt", "issue/5-x", 5)
    (linked / ".factory" / "5" / "plan.md").write_text(
        "---\nticket: 5\nproof:\n  suite: null\n---\n", encoding="utf-8"
    )
    entry = main / ".git" / "worktrees" / "wt"
    entry.mkdir(parents=True)
    (entry / "gitdir").write_text(str(linked / ".git"), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr("factory.cli._source_changed", lambda root: root == linked)
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"cwd": str(main / "botting")}))
    )

    assert main_cli(["hook", "stop"]) == ExitCode.OK
    assert _hook_answer(capsys)["decision"] == "block"
