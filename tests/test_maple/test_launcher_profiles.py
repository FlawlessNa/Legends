"""
The launcher's profile loading, after the leeching and mule bots were removed.

A profile with a `mules:` key used to launch a second Engine group. It now has
to fail legibly, not be silently ignored.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from maple.launchers import profile, run
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


def test_the_example_profile_loads_and_resolves_to_the_training_bot() -> None:
    loaded = profile.load("example")

    assert loaded.main.bot == "training"
    assert loaded.main.settings
    assert run._resolve(loaded.main).__name__ == "TrainingBot"


def _spec(bot: str) -> profile.BotSpec:
    return profile.BotSpec(ign="Main", bot=bot)


def test_a_module_class_bot_resolves_from_a_module_on_sys_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "throwaway_bot_mod.py").write_text(
        "from maple.bots.maple_bot import MapleBot\nclass MyBot(MapleBot):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    cls = run._resolve(_spec("throwaway_bot_mod:MyBot"))

    assert cls.__name__ == "MyBot"


def test_a_module_class_bot_that_is_not_a_maplebot_names_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "throwaway_notbot.py").write_text("class Plain:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(profile.ProfileError, match="throwaway_notbot:Plain"):
        run._resolve(_spec("throwaway_notbot:Plain"))


def test_a_module_class_bot_with_a_missing_attribute_names_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "throwaway_noattr.py").write_text("X = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(profile.ProfileError, match="throwaway_noattr:Missing"):
        run._resolve(_spec("throwaway_noattr:Missing"))


def test_a_module_that_raises_on_import_is_a_profile_error_chaining_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "throwaway_boom.py").write_text("raise ZeroDivisionError('boom')\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(profile.ProfileError, match="throwaway_boom") as info:
        run._resolve(_spec("throwaway_boom:Anything"))

    assert isinstance(info.value.__cause__, ZeroDivisionError)


def test_a_registry_name_still_resolves() -> None:
    assert run._resolve(_spec("training")).__name__ == "TrainingBot"
