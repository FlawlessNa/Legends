"""The dispatcher's contract: exit codes, and the two output forms."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory import __version__
from factory.cli import COMMANDS, build_parser, main
from factory.exit_codes import ExitCode
from factory.models import TABLE_PATH


def test_the_exit_codes_are_the_documented_contract() -> None:
    """The numbers are the interface; hooks and CI branch on them."""
    assert (ExitCode.OK, ExitCode.GATE_FAILED) == (0, 1)
    assert (ExitCode.MISUSE, ExitCode.NEEDS_HUMAN) == (2, 3)


def test_misuse_shares_argparse_s_own_failure_code() -> None:
    """A bad invocation and a refused one report the same thing to the caller."""
    with pytest.raises(SystemExit) as caught:
        main(["no-such-command"])
    assert caught.value.code == ExitCode.MISUSE


def test_no_command_is_misuse_not_success() -> None:
    """A bare `factory` has done nothing, so it must not look like it succeeded."""
    assert main([]) == ExitCode.MISUSE


def test_version_reports_the_factory_s_own_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["version"]) == ExitCode.OK
    assert capsys.readouterr().out.strip() == f"version: {__version__}"


def test_json_renders_the_same_payload_as_one_object(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every command speaks both forms, so an agent never parses prose."""
    assert main(["--json", "version"]) == ExitCode.OK
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
    assert main(["--json", "model", "--stage", "design"]) == ExitCode.OK
    assert _payload(capsys)["model"] == "opus"


def test_model_names_the_rule_that_fired(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without this a human cannot ask why a stage got the model it got."""
    assert main(["--json", "model", "--stage", "qa"]) == ExitCode.OK
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
    assert main(["--json", "model", "--stage", "integrate"]) == ExitCode.OK
    assert _payload(capsys)["model"] is None


def test_an_unknown_stage_is_misuse(repo: Path) -> None:
    """`maintain` is the real case: in `stages.md`, in no enum, owned by no role."""
    assert main(["model", "--stage", "maintain"]) == ExitCode.MISUSE


def test_no_ticket_and_no_stage_is_misuse(repo: Path) -> None:
    """There is no stage to answer about; guessing one would be worse."""
    assert main(["model"]) == ExitCode.MISUSE


def test_a_broken_table_needs_a_human_not_a_misuse(repo: Path) -> None:
    """
    The distinction the Foreman branches on: MISUSE means "I asked wrongly",
    and its documented remedy -- re-read `factory next` -- is useless advice
    for a corrupt config file.
    """
    (repo / TABLE_PATH).write_text('unavailable = ["fabel"]\n', encoding="utf-8")
    assert main(["model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN


def test_a_missing_table_needs_a_human(repo: Path) -> None:
    (repo / TABLE_PATH).unlink()
    assert main(["model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN


def test_no_error_path_ever_reports_a_model(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A silent fallback to the strong model turns a typo into a bill."""
    (repo / TABLE_PATH).write_text("tiers = 3\n", encoding="utf-8")
    assert main(["--json", "model", "--stage", "design"]) == ExitCode.NEEDS_HUMAN
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
    assert main(["--json", "model", "7"]) == ExitCode.OK
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
    assert main(["--json", "model", "7"]) == ExitCode.NEEDS_HUMAN
    assert _payload(capsys)["blocked_by"]
