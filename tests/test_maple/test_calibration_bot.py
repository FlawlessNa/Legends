"""
What the calibration bot's profile needs, and the Swordsman it names.
"""

from typing import Any

import pytest

from maple.bots import CalibrationBot, TrainingBot
from maple.model.characters import MAPPING, Swordsman
from maple.screen import client


def _settings(**more: Any) -> dict[str, Any]:  # noqa: ANN401 - profile settings
    return {
        "map": "auto",
        "character_class": "Swordsman",
        "trial_schedule": "physics",
        **more,
    }


def test_swordsman_is_a_class_a_profile_can_name_with_no_skills() -> None:
    assert MAPPING["Swordsman"] is Swordsman
    assert Swordsman.skills == {}
    assert Swordsman.main_stat == "STR"


def test_the_documented_calibration_profile_has_no_models_path() -> None:
    # The docstring's example: `ign`, `map`, `character_class`, `trial_schedule`.
    bot = CalibrationBot("Someone", {}, **_settings())  # pyright: ignore[reportArgumentType] - metadata is never read here

    assert bot.models_path is None
    assert bot.character_class is Swordsman


def test_a_bot_that_hits_mobs_still_needs_a_models_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "find_window", lambda *_: 4242)
    bot = TrainingBot("Someone", {}, **_settings(mobs=["Bubbling"]))  # pyright: ignore[reportArgumentType] - metadata is never read here

    with pytest.raises(ValueError, match="models_path"):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - nothing else is read before the refusal
