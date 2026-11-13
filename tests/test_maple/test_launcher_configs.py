"""
What the launcher checks before it starts a Session: the two config files the
peripherals read.
"""

from pathlib import Path

import pytest

from maple.launchers import run
from maple.launchers.profile import ProfileError


def _configs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *present: str) -> None:
    for name in present:
        (tmp_path / f"{name}.ini").write_text("", encoding="utf-8")
    monkeypatch.setattr(run, "_config_path", lambda name: str(tmp_path / f"{name}.ini"))


def test_a_missing_recordings_ini_refuses_the_start_and_names_the_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configs(monkeypatch, tmp_path, "discord")

    with pytest.raises(ProfileError, match=r"recordings\.example\.ini"):
        run.check_configs()


def test_a_missing_discord_ini_runs_without_discord_and_says_so_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configs(monkeypatch, tmp_path, "recordings")

    assert run.check_configs() is False

    err = capsys.readouterr().err
    assert err.count("without Discord") == 1
    assert "discord.example.ini" in err


def test_both_files_present_leaves_discord_on_and_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configs(monkeypatch, tmp_path, "recordings", "discord")

    assert run.check_configs() is True
    assert capsys.readouterr().err == ""
