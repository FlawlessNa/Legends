"""How a MapleBot finds its client, and why it needs its job from the profile."""

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from botting.core import Bot, DecisionMaker
from botting.screen import Frame
from maple.bots import maple_bot
from maple.bots.maple_bot import MapleBot
from maple.model.mechanics.physics import Calibration
from maple.screen import client
from maple.screen.map_identification import MapCanvas, MapCanvases
from maple.screen.minimap import MINIMAP, minimap_canvas_path
from maple.screen.minimap_title import MINIMAP_TITLE_READER
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

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, file_map_id: int | None
    ) -> None:
        self.readers: list[Declaration] = []
        self.profiles: list[Profile] = []
        self.checked: list[int | None] = []
        self.sprites = ReaderSprites(None)
        monkeypatch.setattr(
            maple_bot.MinimapEditsManager,
            "from_json",
            lambda name: SimpleNamespace(map_id=file_map_id),
        )
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

    def _check(
        self, sprites: ReaderSprites, file_map_id: int | None
    ) -> tuple[int, ReaderSprites]:
        self.checked.append(file_map_id)
        return 10002000, sprites


def test_child_init_publishes_the_map_settings_id_not_the_map_files_once_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch, file_map_id=999)
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)
    bot = _bot(map="Victoria Road: Ellinia", game_map="Line1Area1")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.map_id == 10002000
    assert start.profiles[0].map_id == 10002000
    assert start.checked == [999]


def test_a_named_map_is_checked_on_screen_with_the_minimap_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch, file_map_id=None)
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_, game_map: 10002000)

    with pytest.raises(_Stop):
        _bot(map="Victoria Road: Ellinia", game_map="Line1Area1").child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert start.readers == [FRAME_CHECK, MINIMAP]
    assert start.checked == [None]


def test_auto_loads_the_titles_glyphs_and_publishes_the_map_identified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = _Start(monkeypatch, file_map_id=None)
    bot = _bot(map="auto", game_map="Line1Area1")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert start.readers == [FRAME_CHECK, MINIMAP, MINIMAP_TITLE_READER]
    assert start.profiles[0].map_id is None
    assert bot.data is not None
    assert bot.data.map_id == 10002000


def test_a_map_file_alone_is_not_checked_at_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only `map` asks for the check; a profile naming only its map file starts
    as before, `CheckStillInMap` alone watching the map."""
    start = _Start(monkeypatch, file_map_id=999)
    bot = _bot(game_map="Line1Area1")

    with pytest.raises(_Stop):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType]

    assert start.readers == []
    assert start.checked == []
    assert bot.data is not None
    assert bot.data.map_id == 999


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
    bot.game_map = "Line1Area1"
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

    map_id, sprites = bot._check_map_at_start(
        _sprites_without_the_maps_canvases(), None
    )

    assert map_id == MAP_ID
    assert sprites.canvas(minimap_canvas_path(MAP_ID)).rgba is CANVAS.rgba
    assert bot.shown == [True]  # pyright: ignore[reportAttributeAccessIssue]


def test_auto_refuses_when_the_map_file_is_another_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _on_screen(monkeypatch, _showing(), map_auto=True, map_id=None)

    with pytest.raises(
        StartupRefused, match=f"map file 'Line1Area1' is map {OTHER_MAP_ID}"
    ):
        bot._check_map_at_start(_sprites_without_the_maps_canvases(), OTHER_MAP_ID)


def test_a_named_map_starts_on_its_own_minimap(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = _on_screen(monkeypatch, _showing(), map_auto=False, map_id=MAP_ID)

    sprites = title_sprites()
    assert bot._check_map_at_start(sprites, None) == (MAP_ID, sprites)
    assert bot.shown == [False]  # pyright: ignore[reportAttributeAccessIssue]


def test_a_named_map_refuses_another_maps_minimap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _on_screen(monkeypatch, _showing(OTHER_CANVAS), map_auto=False, map_id=MAP_ID)

    with pytest.raises(StartupRefused, match=f"another map than map {MAP_ID}"):
        bot._check_map_at_start(title_sprites(), None)


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
