"""How a MapleBot finds its client, and what it needs from the profile: its job,
its map and the mobs it looks for."""

import logging
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from botting.core import Bot, DecisionMaker
from botting.screen import Frame
from game_data.catalogue import Bounds
from maple.bots import maple_bot
from maple.bots.maple_bot import MapleBot
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.launchers.profile import ProfileError
from maple.model.mechanics.physics import Calibration
from maple.model.world import MinimapTransform, WorldMap
from maple.screen import client
from maple.screen.map_identification import MapCanvas, MapCanvases
from maple.screen.minimap import MINIMAP, minimap_canvas_path
from maple.screen.minimap_title import MINIMAP_TITLE_READER
from maple.screen.position import PositionFusion
from maple.screen.sprites import (
    FRAME_CHECK,
    Declaration,
    Profile,
    ReaderSprites,
    StartupRefused,
)
from tests.test_maple.test_screen_minimap import (
    CANVAS,
    MAP_ID,
    OTHER_CANVAS,
    OTHER_MAP_ID,
    draw_minimap,
    frame,
    screen,
)
from tests.test_maple.test_screen_minimap_title import (
    FRAME_AT,
    TITLE,
    draw_title,
    title_sprites,
)


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
    bot = _Bot("Someone", {}, map="auto", character_class="Bishop")  # pyright: ignore[reportArgumentType] - metadata is never read here

    assert bot.find_handle() == 4242
    assert calls == [("MapleStoryClass", "MapleStory.exe")]


def test_construction_without_character_class_names_the_profile_key() -> None:
    with pytest.raises(ValueError, match="character_class"):
        _Bot("Someone", {}, map="auto")  # pyright: ignore[reportArgumentType] - metadata is never read here


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
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="Victoria Road: Ellinia",
        character_class="Bishop",
    )

    assert bot.map_id == 10002000


def test_game_map_is_refused_naming_map_and_mobs() -> None:
    """The map files are retired (#399): a profile still naming one refuses the
    start, saying what replaces it."""
    with pytest.raises(ProfileError, match=r"`map`.*`mobs`"):
        _Bot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            game_map="Line1Area1",
            character_class="Bishop",
        )


def test_a_profile_without_map_is_refused() -> None:
    with pytest.raises(ProfileError, match="need `map`"):
        _Bot("Someone", {}, character_class="Bishop")  # pyright: ignore[reportArgumentType] - metadata is never read here


def test_mobs_must_be_a_list() -> None:
    with pytest.raises(ProfileError, match=r"\[Bubbling\]"):
        _Bot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            character_class="Bishop",
            mobs="Bubbling",
        )


class _TrainingBot(_Bot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [MobsHitting]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]


@pytest.mark.parametrize("mobs", [None, []])
def test_a_training_bot_without_mobs_warns_once(
    caplog: pytest.LogCaptureFixture, mobs: list[str] | None
) -> None:
    with caplog.at_level(logging.WARNING, logger=maple_bot.logger.name):
        _TrainingBot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            character_class="Bishop",
            mobs=mobs,
        )

    (message,) = _warnings(caplog)
    assert "Someone" in message
    assert "`mobs`" in message


def test_a_training_bot_with_mobs_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=maple_bot.logger.name):
        _TrainingBot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            character_class="Bishop",
            mobs=["Bubbling"],
        )

    assert _warnings(caplog) == []


def test_a_bot_that_does_not_train_may_have_no_mobs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=maple_bot.logger.name):
        _bot(map="auto")

    assert _warnings(caplog) == []


def _bot(**settings: Any) -> _Bot:  # noqa: ANN401 - profile settings
    return _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        character_class="Bishop",
        models_path={},
        **settings,
    )


class _Start:
    """What `child_init` loaded and checked, up to the first reader attribute,
    where it stops."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.readers: list[Declaration] = []
        self.profiles: list[Profile] = []
        self.checked = 0
        self.sprites = ReaderSprites(None)
        monkeypatch.setattr(maple_bot, "load_reader_sprites", self._load)
        monkeypatch.setattr(MapleBot, "_check_map_at_start", self._check)
        monkeypatch.setattr(client, "find_window", lambda *_: 4242)
        monkeypatch.setattr(
            maple_bot.InGameDetectionVisuals,
            "register_models",
            lambda *_: (_ for _ in ()).throw(_Stop()),
        )

    def _load(self, readers: Sequence[Declaration], profile: Profile) -> ReaderSprites:
        self.readers = list(readers)
        self.profiles.append(profile)
        return self.sprites

    def _check(self, sprites: ReaderSprites) -> tuple[int, ReaderSprites]:
        self.checked += 1
        return 10002000, sprites


def test_child_init_publishes_the_map_settings_id_once_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch)
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)
    bot = _bot(map="Victoria Road: Ellinia")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.map_id == 10002000
    assert start.profiles[0].map_id == 10002000
    assert start.checked == 1


def test_a_named_map_is_checked_on_screen_with_the_minimap_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch)
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)

    with pytest.raises(_Stop):
        _bot(map="Victoria Road: Ellinia").child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert start.readers == [FRAME_CHECK, MINIMAP]
    assert start.checked == 1


def test_auto_loads_the_titles_glyphs_and_publishes_the_map_identified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch)
    bot = _bot(map="auto")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert start.readers == [FRAME_CHECK, MINIMAP, MINIMAP_TITLE_READER]
    assert start.profiles[0].map_id is None
    assert bot.data is not None
    assert bot.data.map_id == 10002000


@pytest.mark.parametrize(
    ("settings", "names"),
    [({"mobs": ["Bubbling", "PacPinky"]}, ["Bubbling", "PacPinky"]), ({}, [])],
)
def test_current_mobs_are_the_profiles_mobs_and_none_without_them(
    monkeypatch: pytest.MonkeyPatch, settings: dict[str, Any], names: list[str]
) -> None:
    """What a map file's `mobs` list was: the detection classes to look for. A
    profile naming none looks for none, as a map file with an empty list did."""
    _Start(monkeypatch)
    monkeypatch.setattr(
        maple_bot.InGameDetectionVisuals, "register_models", lambda *_: None
    )
    monkeypatch.setattr(
        maple_bot.InGameDetectionVisuals, "register_cache_id", lambda *_: None
    )
    bot = _bot(map="auto", **settings)

    bot.child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert bot.data is not None
    assert [type(mob).__name__ for mob in bot.data.current_mobs] == names


def _world_map(map_id: int, minimap: MinimapTransform | None) -> WorldMap:
    return WorldMap(map_id, None, None, Bounds(0, 0, 100, 100), minimap, (), (), (), ())


@pytest.mark.parametrize("minimap", [MinimapTransform((10, 20), 4), None])
def test_child_init_builds_the_world_map_from_the_map_id_it_publishes(
    monkeypatch: pytest.MonkeyPatch, minimap: MinimapTransform | None
) -> None:
    """With the store the readers' sprites came from, and that store's
    `Physics.img` values, which Movement Plans derive their physics from; and
    the position's reader on it, when the map has a minimap to check positions
    against."""
    start = _Start(monkeypatch)
    start.sprites = ReaderSprites("build")
    loaded: list[int] = []

    def load(map_id: int) -> WorldMap:
        loaded.append(map_id)
        return _world_map(map_id, minimap)

    physics = {"walkSpeed": 125.0, "jumpSpeed": 555.0}
    monkeypatch.setattr(maple_bot.WorldMap, "load", load)
    monkeypatch.setattr(maple_bot, "game_physics", lambda: physics)
    monkeypatch.setattr(maple_bot, "FrameCheck", lambda sprites: object())
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)
    bot = _bot(map="Victoria Road: Ellinia")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert bot.data is not None
    assert loaded == [bot.data.map_id] == [10002000]
    assert bot.data.world_map.id == 10002000
    assert bot.data.game_physics is physics
    if minimap is None:
        assert bot.data.position_fusion is None
    else:
        assert isinstance(bot.data.position_fusion, PositionFusion)


# --- The check itself, on synthetic frames ------------------------------------


def _on_screen(
    monkeypatch: pytest.MonkeyPatch, drawn: Frame, map_auto: bool, map_id: int | None
) -> MapleBot:
    """A bot past `Bot.child_init`, whose client shows `drawn`, and whose minimap
    key is never pressed."""
    source = SimpleNamespace(grab=lambda handle: drawn)
    monkeypatch.setattr(maple_bot, "frame_source", lambda: source)
    shown: list[bool] = []
    monkeypatch.setattr(
        MapleBot, "_show_minimap", lambda self, minimap, banner: shown.append(banner)
    )
    monkeypatch.setattr(
        MapCanvases,
        "load",
        classmethod(
            lambda cls: MapCanvases(
                [
                    MapCanvas.of(MAP_ID, TITLE, CANVAS),
                    MapCanvas.of(OTHER_MAP_ID, "Cc: Ab", OTHER_CANVAS),
                ]
            )
        ),
    )
    bot = object.__new__(_Bot)
    bot.ign = "Someone"
    bot.map_auto = map_auto
    bot.map_id = map_id
    bot.data = SimpleNamespace(handle=4242)  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    bot.shown = shown  # pyright: ignore[reportAttributeAccessIssue] - kept for the test
    return bot


def _showing(drawn_canvas: object = CANVAS) -> Frame:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT, canvas=drawn_canvas)  # pyright: ignore[reportArgumentType]
    draw_title(pixels)
    return frame(pixels)


def _sprites_without_the_maps_canvases() -> ReaderSprites:
    s = title_sprites()
    for map_id in (MAP_ID, OTHER_MAP_ID):
        del s.canvases[minimap_canvas_path(map_id)]
    return s


def test_auto_identifies_the_map_and_adds_its_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _on_screen(monkeypatch, _showing(), map_auto=True, map_id=None)

    map_id, sprites = bot._check_map_at_start(_sprites_without_the_maps_canvases())

    assert map_id == MAP_ID
    assert sprites.canvas(minimap_canvas_path(MAP_ID)).rgba is CANVAS.rgba
    assert bot.shown == [True]  # pyright: ignore[reportAttributeAccessIssue]


def test_a_named_map_starts_on_its_own_minimap(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _on_screen(monkeypatch, _showing(), map_auto=False, map_id=MAP_ID)

    sprites = title_sprites()
    assert bot._check_map_at_start(sprites) == (MAP_ID, sprites)
    assert bot.shown == [False]  # pyright: ignore[reportAttributeAccessIssue]


def test_a_named_map_refuses_another_maps_minimap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _on_screen(monkeypatch, _showing(OTHER_CANVAS), map_auto=False, map_id=MAP_ID)

    with pytest.raises(StartupRefused, match=f"another map than map {MAP_ID}"):
        bot._check_map_at_start(title_sprites())


def test_when_the_banner_cant_be_shown_any_expanded_minimap_will_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[bool] = []

    def ensure(*_: object, banner: bool) -> None:
        asked.append(banner)
        if banner:
            raise TimeoutError("toggle failed validation")

    monkeypatch.setattr(maple_bot, "ensure_minimap_displayed", ensure)
    monkeypatch.setattr(
        maple_bot.ProxyFactory, "instance", lambda self, owner, kind: object()
    )
    bot = object.__new__(_Bot)
    bot.ign = "Someone"
    bot.metadata = {}  # pyright: ignore[reportAttributeAccessIssue] - never read
    bot.pipe = object()  # pyright: ignore[reportAttributeAccessIssue] - never read
    bot.data = SimpleNamespace(handle=4242)  # pyright: ignore[reportAttributeAccessIssue] - a stand-in

    bot._show_minimap(object(), banner=True)  # pyright: ignore[reportArgumentType] - never read

    assert asked == [True, False]


def test_construction_parses_the_calibration_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="Victoria Road: Ellinia",
        character_class="Bishop",
        calibration={"walk": 1.1, "teleport": 0.9},
    )

    assert bot.calibration == Calibration(walk=1.1, teleport=0.9)
    # It stays out of the kwargs that reach the DecisionMakers.
    assert "calibration" not in bot.kwargs


def test_construction_refuses_a_misspelt_calibration_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: 10002000)
    with pytest.raises(ValueError, match="no constant 'speed'"):
        _Bot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="Victoria Road: Ellinia",
            character_class="Bishop",
            calibration={"speed": 1.1},
        )
