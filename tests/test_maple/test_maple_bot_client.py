"""How a MapleBot finds its client, and why it needs its job from the profile."""

import pytest

from botting.core import Bot, DecisionMaker
from maple.bots.maple_bot import MapleBot
from maple.screen import client


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
