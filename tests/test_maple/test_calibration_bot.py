"""
What the calibration bot's profile needs, and the Swordsman it names.
"""

from pathlib import Path
from typing import Any

import pytest

from maple.bots import CalibrationBot, TrainingBot
from maple.calibration import TrialSpecError
from maple.decision_makers import TrialRunner, trial_runner
from maple.decision_makers.providers import (
    ATTACKS,
    HUNTING_AREA,
    AttacksProvider,
    ChatProvider,
    DestinationProvider,
    HuntingAreaProvider,
    MinimapProvider,
    OnScreenPositionProvider,
)
from maple.model.characters import MAPPING, Swordsman
from maple.screen import client
from tests.test_maple import test_screen_minimap as minimap


def _settings(**more: Any) -> dict[str, Any]:  # noqa: ANN401 - profile settings
    return {
        "map": "auto",
        "character_class": "Swordsman",
        "trial_schedule": "physics",
        **more,
    }


def test_swordsman_is_a_class_a_profile_can_name() -> None:
    assert MAPPING["Swordsman"] is Swordsman
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
    bot = TrainingBot("Someone", {}, **_settings())  # pyright: ignore[reportArgumentType] - metadata is never read here

    with pytest.raises(ValueError, match="models_path"):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - nothing else is read before the refusal


def test_its_trial_runner_assembles_with_the_destination_and_no_chat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    `TrialRunner` steers `DESTINATION`, so assembly builds its Provider, after
    the minimap's, on a bot that reads no chat and finds no character on
    screen; then the runner's `setup()` checks the schedule's map. The training
    bot's synthetic client is used (its map has no minimap, so that check is
    what stops it), running the calibration bot's one DecisionMaker, with no
    `attacks`, as a calibration profile has none.

    The Destination Provider's sources read the Hunting Area's keys, so their
    Providers are built too (#579): with no `hunting_area` rotation they open no
    window and read no marker.
    """
    from tests.test_maple import test_training_bot as training

    asked = training.watch_the_hunting_area(monkeypatch)
    monkeypatch.setattr(TrainingBot, "_decision_makers", lambda self: [TrialRunner])
    monkeypatch.setattr(trial_runner.Catalogue, "latest", lambda: _NoCatalogue())
    monkeypatch.setattr(
        trial_runner, "schedule_map_id", lambda schedule, catalogue: minimap.MAP_ID
    )
    bot, _, _, _ = training._start(
        monkeypatch,
        trial_schedule="physics",
        record_path=str(tmp_path / "record.jsonl"),
        attacks=None,
    )

    with pytest.raises(TrialSpecError, match="no minimap"):
        bot.assemble()

    built = [type(p) for p in bot.providers]
    assert built.index(MinimapProvider) < built.index(DestinationProvider)
    assert ChatProvider not in built
    assert OnScreenPositionProvider not in built
    assert {HuntingAreaProvider, AttacksProvider} <= set(built)
    data = bot.data
    assert data is not None
    assert data.read(HUNTING_AREA) is None
    assert data.read(ATTACKS) is None
    assert set(asked) <= {()}, "no read asked for a marker"


class _NoCatalogue:
    def __enter__(self) -> object:
        return self

    def __exit__(self, *_: object) -> None:
        return None
