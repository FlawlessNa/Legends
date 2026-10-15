"""The dispatcher's contract: exit codes, and the two output forms."""

from __future__ import annotations

import json

import pytest

from factory import __version__
from factory.cli import COMMANDS, build_parser, main
from factory.exit_codes import ExitCode


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
