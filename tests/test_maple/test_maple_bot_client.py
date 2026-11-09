"""How a MapleBot finds its client, and why it needs its job from the profile."""

from types import SimpleNamespace

import pytest

from botting.core import Bot, DecisionMaker
from maple.bots import maple_bot
from maple.bots.maple_bot import MapleBot
from maple.model.mechanics.physics import Calibration
from maple.screen import client
from maple.screen.sprites import Profile


class _Stop(Exception):
    pass


class _Bot(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return []


def test_find_handle_uses_class_name_and_executable_from_game_ini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _find_window(class_name: str, executable: str) -> int:
        calls.append((class_name, executable))
        return 4242

    monkeypatch.setattr(client, "find_window", _find_window)
    bot = _Bot("Someone", {}, game_map="Line1Area1", character_class="Bishop")  # pyright: ignore[reportArgumentType] - metadata is never read here

    assert bot.find_handle() == 4242
    assert calls == [("MapleStoryClass", "MapleStory.exe")]


def test_construction_without_character_class_names_the_profile_key() -> None:
    with pytest.raises(ValueError, match="character_class"):
        _Bot("Someone", {}, game_map="Line1Area1")  # pyright: ignore[reportArgumentType] - metadata is never read here


def test_child_init_takes_the_handle_from_find_handle() -> None:
    class _Found(Bot):
        def find_handle(self) -> int:
            return 77

        def _decision_makers(self) -> list[type[DecisionMaker]]:
            return []

    bot = _Found("Someone", {})  # pyright: ignore[reportArgumentType] - metadata is never read here
    bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.handle == 77


def test_construction_reads_the_map_setting_and_stores_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="Victoria Road: Ellinia",
        game_map="Line1Area1",
        character_class="Bishop",
    )

    assert bot.map_id == 10002000
    assert bot.game_map == "Line1Area1"


def test_child_init_publishes_the_map_settings_id_not_the_map_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Profile] = []
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)
    monkeypatch.setattr(
        maple_bot.MinimapEditsManager,
        "from_json",
        lambda name: SimpleNamespace(map_id=999),
    )

    def _load(_readers: object, profile: Profile) -> None:
        seen.append(profile)
        raise _Stop

    monkeypatch.setattr(maple_bot, "load_reader_sprites", _load)
    monkeypatch.setattr(client, "find_window", lambda *_: 4242)
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="Victoria Road: Ellinia",
        game_map="Line1Area1",
        character_class="Bishop",
        models_path={},
    )

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.map_id == 10002000
    assert seen[0].map_id == 10002000


def test_construction_parses_the_calibration_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="Victoria Road: Ellinia",
        game_map="Line1Area1",
        character_class="Bishop",
        calibration={"walk": 1.1, "teleport": 0.9},
    )

    assert bot.calibration == Calibration(walk=1.1, teleport=0.9)
    # It stays out of the kwargs that reach `MapleMap` and the DecisionMakers.
    assert "calibration" not in bot.kwargs


def test_construction_refuses_a_misspelt_calibration_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)
    with pytest.raises(ValueError, match="no constant 'speed'"):
        _Bot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="Victoria Road: Ellinia",
            game_map="Line1Area1",
            character_class="Bishop",
            calibration={"speed": 1.1},
        )
