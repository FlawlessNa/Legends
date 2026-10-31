"""
The launcher's profile loading, after the leeching and mule bots were removed.

A profile with a `mules:` key used to launch a second Engine group. It now has
to fail legibly, not be silently ignored.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from maple.launchers import profile
from paths import ROOT


def test_a_profile_with_a_mules_key_fails_and_says_mules_were_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "old.yaml").write_text(
        "ign: Main\nbot: TrainingBot\nmules:\n  - ign: Mule\n    bot: TrainingBot\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(profile, "PROFILES_DIR", str(tmp_path))

    with pytest.raises(profile.ProfileError, match="Mules were removed"):
        profile.load("old")


def test_list_exits_zero_and_lists_the_example_profile() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maple.launchers.run", "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "example" in result.stdout.split()
