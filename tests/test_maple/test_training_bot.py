"""
`TrainingBot` on the new readers, against a synthetic frame source: one frame
that draws the status bar, the quick slots, the minimap, two buffs and the
chat, composed from each reader's synthetic sprites (no client pixels).

The bot starts as `Engine` starts it (`child_init`, then its assembly, which
builds its Providers and its DecisionMakers), with the store, the Main Process
proxies, the keybindings and the pipe stubbed. Each DecisionMaker then makes one decision; their task loops, which
need Main Process to answer, are not run. Every reader the DecisionMakers name
must read.

`ChatReplies` replies by default: its check of the model is scripted, as
`_Model`, so no test reaches the network.
"""

import asyncio
import queue
import threading
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pytest

from botting import controller
from botting.core import (
    ActionRequest,
    DecisionMaker,
    ProxyFactory,
    RepliesProvider,
    WindowProvider,
)
from botting.core.supervisor import USER
from botting.screen import Frame, Reading, Status, capture
from game_data.catalogue import Bounds, Foothold
from game_data.sprites import Sprite
from maple.actions.menus import toggle_minimap
from maple.bots import maple_bot
from maple.bots.training import TrainingBot
from maple.decision_makers import (
    ChatReplies,
    CheckMobsStillSpawn,
    CheckStillInMap,
    MobsHitting,
    PetFood,
    Rotation,
    SoloRebuff,
)
from maple.decision_makers import chat_replies as chat_replies_module
from maple.decision_makers.providers import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    FRAME,
    HUNTING_AREA,
    MINIMAP_BOX,
    BuffsProvider,
    CastReachProvider,
    CharacterProvider,
    ChatProvider,
    ClientProvider,
    DestinationProvider,
    HuntingAreaProvider,
    MapProvider,
    MinimapProvider,
    MobsProvider,
    OnScreenPositionProvider,
    OtherPlayersProvider,
    PathingProvider,
    ProfileProvider,
    QuickSlotsProvider,
    ScreenReadersProvider,
    StatusBarProvider,
)
from maple.launchers import hunting_area_window
from maple.model.world import WorldMap, chain_platforms
from maple.screen import client
from maple.screen.buffs import BUFFS
from maple.screen.chat import CHAT, ChatKind, ChatLine
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapView
from maple.screen.name_tag import NAME_TAGS
from maple.screen.quick_slots import QUICK_SLOTS
from maple.screen.sprites import (
    FRAME_CHECK,
    GAUGE_LABEL,
    Declaration,
    Profile,
    ReaderSprites,
    StartupRefused,
)
from maple.screen.status_bar import (
    _EXP_AT,  # pyright: ignore[reportPrivateUsage]
    _GAUGE_GLYPHS,  # pyright: ignore[reportPrivateUsage]
    _HP_AT,  # pyright: ignore[reportPrivateUsage]
    _LEVEL_AT,  # pyright: ignore[reportPrivateUsage]
    _LEVEL_DIGITS,  # pyright: ignore[reportPrivateUsage]
    _MP_AT,  # pyright: ignore[reportPrivateUsage]
    BACKGROUND,
    STATUS_BAR,
)
from maple.telemetry_events import CHAT_GM_LINE
from tests.test_maple import (
    test_screen_buffs as buffs,
)
from tests.test_maple import (
    test_screen_chat as chat,
)
from tests.test_maple import (
    test_screen_minimap as minimap,
)
from tests.test_maple import (
    test_screen_quick_slots as quick_slots,
)
from tests.test_maple import (
    test_screen_status_bar as status_bar,
)
from tests.test_maple.movement_lab.corpus import LAB_PHYSICS_VALUES

WIDTH, HEIGHT = 1024, 768
BUFF_NAMES = ("Magic Guard", "Invincible")
MINIMAP_AT = (20, 20)
USER_AT = (30, 30)
"""The player marker, in pixels of the minimap's canvas: on the map's floor."""
CHAT_AT = (40, 600)
STATUS_BAR_AT = (30, 700)


def _sprites(profile: Profile) -> ReaderSprites:
    """Every reader's synthetic sprites, with the status bar's gauge label as
    the one frame-check anchor, and an icon for each of the profile's buffs."""
    canvases: dict[str, Sprite] = {}
    for module_sprites in (
        quick_slots.sprites(),
        minimap.sprites(),
        buffs.build_sprites(),
        chat.sprites(),
        status_bar.SPRITES,
    ):
        canvases.update(module_sprites.canvases)
    icons = dict(zip(profile.buffs, buffs.ICONS.values(), strict=False))
    assert len(icons) == len(profile.buffs) == len(BUFF_NAMES)
    return ReaderSprites(
        "synthetic",
        canvases,
        dict(status_bar.VECTORS),
        {name: Sprite(name, rgba, (0, buffs.SIZE)) for name, rgba in icons.items()},
        chat.sprites().glyph_sets,
    )


def _draw_status_bar(pixels: np.ndarray) -> None:
    x, y = STATUS_BAR_AT
    bg_x, bg_y = status_bar.BACKGROUND_ORIGIN
    status_bar.paste(pixels, status_bar.sprite_of(BACKGROUND).rgba, x - bg_x, y - bg_y)
    label_x, label_y = status_bar.LABEL_ORIGIN
    status_bar.paste(
        pixels, status_bar.sprite_of(GAUGE_LABEL).rgba, x - label_x, y - label_y
    )
    for text, glyphs, at in (
        ("123", _LEVEL_DIGITS, _LEVEL_AT),
        ("[1500/2000]", _GAUGE_GLYPHS, _HP_AT),
        ("[300/450]", _GAUGE_GLYPHS, _MP_AT),
        ("98765[12.34%]", _GAUGE_GLYPHS, _EXP_AT),
    ):
        cx, cy = x + status_bar.VECTORS[at][0], y + status_bar.VECTORS[at][1]
        for char in text:
            rgba = status_bar.sprite_of(glyphs[char]).rgba
            status_bar.paste(pixels, rgba, cx, cy)
            cx += rgba.shape[1]


def _screen() -> np.ndarray:
    pixels = np.full((HEIGHT, WIDTH, 3), 40, dtype=np.uint8)
    minimap.draw_minimap(pixels, *MINIMAP_AT, user_at=USER_AT)
    for key, (row, column) in quick_slots.GRID.items():
        quick_slots.draw_label(pixels, key, row, column)
    quick_slots.draw_count(pixels, 57, 0, 2)
    for i, rgba in enumerate(list(buffs.ICONS.values())[: len(BUFF_NAMES)]):
        buffs.draw(pixels, rgba, WIDTH - 3 - buffs.SIZE * (i + 1), 3)
    chat.draw_chat(pixels, [chat.Row(text="Hi!")], point=CHAT_AT)
    _draw_status_bar(pixels)
    return pixels


class _Source:
    """A `FrameSource` that always shows the same screen, a few seconds apart,
    so the quick slots settle after two reads."""

    def __init__(self) -> None:
        self.pixels = _screen()
        self.grabs = 0

    def grab(self, handle: int) -> Frame:
        self.grabs += 1
        return Frame(self.pixels, (WIDTH, HEIGHT), 3.0 * self.grabs, True, True)


class _Pipe:
    def __init__(self) -> None:
        self.sent: list[ActionRequest] = []

    def send(self, request: ActionRequest) -> None:
        self.sent.append(request)


class _Model:
    """The model `ChatReplies` checks at start: reachable unless `cause`."""

    cause: str | None = None

    async def ask(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("no test here asks the model")

    async def check(self) -> str | None:
        return self.cause


Started = tuple[TrainingBot, "_Source", "_Pipe", list[Declaration]]


@pytest.fixture
def start(monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    """Starts the bot, with the profile's settings plus `settings`."""
    return lambda **settings: _start(monkeypatch, **settings)


@pytest.fixture
def started(start: Any) -> Started:  # noqa: ANN401
    return start()


def _start(
    monkeypatch: pytest.MonkeyPatch,
    **settings: Any,  # noqa: ANN401 - a profile setting is any value
) -> Started:
    monkeypatch.setattr(chat_replies_module, "AnthropicModel", _Model)
    source = _Source()
    monkeypatch.setattr(capture, "_source", source)
    monkeypatch.setattr(client, "find_window", lambda *_: 4242)
    # The synthetic minimap's map, as the profile would name it; the check at
    # start that the minimap shows it is `test_maple_bot_client`'s.
    monkeypatch.setattr(maple_bot, "resolve_map_id", lambda map_: minimap.MAP_ID)
    monkeypatch.setattr(
        maple_bot.MapleBot,
        "_check_map_at_start",
        lambda self, sprites: (minimap.MAP_ID, sprites),
    )
    loaded: list[Declaration] = []

    def load(readers: Sequence[Declaration], profile: Profile) -> ReaderSprites:
        loaded.extend(readers)
        return _sprites(profile)

    monkeypatch.setattr(maple_bot, "load_reader_sprites", load)
    # The synthetic map isn't in any store: a map with no minimap, so no
    # position is read on it either, and one floor the rotation picks its
    # targets on.
    floor, _ = chain_platforms([Foothold("map", 0, 0, 1, 0, 0, 700, 0, 0, 0)])
    monkeypatch.setattr(
        maple_bot.WorldMap,
        "load",
        lambda map_id: WorldMap(
            map_id, None, None, Bounds(0, 0, WIDTH, HEIGHT), None, floor, (), (), ()
        ),
    )
    # Nor its physics: Movement Plans' `Physics.img` values, written out.
    monkeypatch.setattr(maple_bot, "game_physics", lambda: dict(LAB_PHYSICS_VALUES))

    def proxy(
        self: ProxyFactory,
        key: str,
        primitive_type: str,
        shared: bool,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> object:
        kind = (
            queue.Queue
            if primitive_type == "Queue"
            else getattr(threading, primitive_type)
        )
        return kind(*args, **kwargs)

    monkeypatch.setattr(ProxyFactory, "_request", proxy)
    monkeypatch.setattr(controller, "key_binds", lambda ign: defaultdict(lambda: "f12"))

    profile: dict[str, Any] = {
        "map": minimap.MAP_ID,
        "character_class": "Bishop",
        "models_path": {},
        "included_buffs": list(BUFF_NAMES),
        "mob_count_threshold": 2,
        "mob_spawn_alert_timer": 60.0,
        "mob_spawn_alert_threshold": 1,
    }
    bot = TrainingBot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - the proxies are stubbed above
        **{**profile, **settings},
    )
    pipe = _Pipe()
    bot.child_init(pipe, None)  # pyright: ignore[reportArgumentType] - no barrier before start()
    return bot, source, pipe, loaded


def _decision_makers(bot: TrainingBot) -> dict[type[DecisionMaker], DecisionMaker]:
    """The bot's DecisionMakers, assembled as `Bot.start` assembles them."""
    if bot.supervisor is None:
        bot.assemble()
    return {type(dm): dm for dm in bot.decision_makers}


def test_every_reader_its_decision_makers_name_is_loaded(
    started: Started,
) -> None:
    _, _, _, loaded = started

    assert loaded[0] == FRAME_CHECK
    assert set(loaded) == {
        FRAME_CHECK,
        STATUS_BAR,
        QUICK_SLOTS,
        MINIMAP,
        BUFFS,
        CHAT,
        NAME_TAGS,
    }


def test_training_bot_starts_on_the_new_readers_and_every_reader_reads(
    started: Started,
) -> None:
    bot, source, pipe, _ = started
    data = bot.data
    assert data is not None

    dms = _decision_makers(bot)
    assert set(dms) == set(bot._decision_makers())  # pyright: ignore[reportPrivateUsage]
    # The Bot-level Providers, in `child_init`'s order, then those assembly
    # builds for what the DecisionMakers read, each after what it needs: the
    # minimap, once, then the on-screen position (`MobsHitting`), the
    # destination, after what its sources read (the other players, the Hunting
    # Area and the cast's reach), and its pathing (`Rotation`), the quick slots
    # (`PetFood`), the buffs (`SoloRebuff`) and the chat (`ChatReplies`).
    assert [type(p) for p in bot.providers] == [
        WindowProvider,
        RepliesProvider,
        ScreenReadersProvider,
        MapProvider,
        CharacterProvider,
        MobsProvider,
        ClientProvider,
        ProfileProvider,
        MinimapProvider,
        OnScreenPositionProvider,
        OtherPlayersProvider,
        HuntingAreaProvider,
        CastReachProvider,
        DestinationProvider,
        PathingProvider,
        QuickSlotsProvider,
        BuffsProvider,
        ChatProvider,
    ]

    async def decide_once() -> None:
        for kind in (
            MobsHitting,
            Rotation,
            PetFood,
            CheckMobsStillSpawn,
            CheckStillInMap,
            ChatReplies,
        ):
            await dms[kind]._decide()  # pyright: ignore[reportPrivateUsage]

    asyncio.run(decide_once())
    rebuff = dms[SoloRebuff]
    assert isinstance(rebuff, SoloRebuff)
    rebuff._read_buffs()  # pyright: ignore[reportPrivateUsage]
    # The status bar's reader is loaded for `PetFood`'s `screen_readers`; no
    # DecisionMaker of this bot reads it, so it is asked for here.
    assert data.providers is not None
    data.providers.ensure(StatusBarProvider)

    assert isinstance(data.read(FRAME), Frame)
    assert source.grabs > 1
    with pytest.raises(AttributeError):
        _ = data.current_client_img

    assert data.status_bar.status is Status.READ, data.status_bar.detail
    assert data.status_bar.value.level == 123
    assert data.quick_slots.status is Status.READ, data.quick_slots.detail
    assert data.quick_slots.value.slot(3).count == 57
    assert data.buffs.status is Status.READ, data.buffs.detail
    assert {name: state.shown for name, state in data.buffs.value.items()} == {
        name: True for name in BUFF_NAMES
    }
    assert data.minimap_reading.status is Status.READ, data.minimap_reading.detail
    minimap_view = data.minimap_reading.value
    assert minimap_view is not None
    assert minimap_view.self_position.value == USER_AT
    assert "current_minimap_position" not in data._managed  # pyright: ignore[reportPrivateUsage]
    assert data.read(MINIMAP_BOX) is not None
    assert data.chat_lines.status is Status.READ, data.chat_lines.detail

    # The minimap was already shown expanded: its key was never pressed.
    assert not [r for r in pipe.sent if r.procedure is toggle_minimap]


# --- the Hunting Area's Providers, with another rotation (#579) ----------------------


def watch_the_hunting_area(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """
    Fail the test if the launch window opens; record the markers each read of
    the minimap asks for.
    """

    def opened(*args: object) -> None:
        raise AssertionError("the launch window opened")

    monkeypatch.setattr(hunting_area_window, "choose_hunting_area", opened)
    asked: list[tuple[str, ...]] = []
    read = MinimapReader.read

    def recorded(
        self: MinimapReader, frame: Frame, markers: Iterable[str] = ()
    ) -> Reading[MinimapView]:
        asked.append(tuple(markers))
        return read(self, frame, markers)

    monkeypatch.setattr(MinimapReader, "read", recorded)
    return asked


def test_a_random_rotation_assembles_with_no_window_opened_and_no_marker_read(
    start: Any,  # noqa: ANN401
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = watch_the_hunting_area(monkeypatch)
    bot, _, _, _ = start(rotation="random")
    data = bot.data
    assert data is not None

    dms = _decision_makers(bot)

    async def decide_once() -> None:
        for kind in (MobsHitting, Rotation, CheckMobsStillSpawn):
            await dms[kind]._decide()  # pyright: ignore[reportPrivateUsage]

    asyncio.run(decide_once())
    built = [type(p) for p in bot.providers]
    assert {HuntingAreaProvider, OtherPlayersProvider, CastReachProvider} <= set(built)
    assert data.read(HUNTING_AREA) is None
    assert data.read(AREA_STRETCHES) is None
    assert data.read(AREA_PRESENCE) is None
    assert asked, "the minimap was read"
    assert set(asked) == {()}, "no read asked for a marker"


# --- chat replies, on by default (#464) ----------------------------------------------


def test_the_bot_refuses_to_start_when_the_model_cant_be_reached(
    start: Any,  # noqa: ANN401
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_Model, "cause", "AuthenticationError: no credentials")
    bot, _, _, _ = start()

    with pytest.raises(StartupRefused, match="no credentials"):
        bot.assemble()


def test_with_chat_replies_false_it_starts_and_the_gm_alarm_still_fires(
    start: Any,  # noqa: ANN401
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_Model, "cause", "AuthenticationError: no credentials")
    bot, _, _, _ = start(chat_replies=False)
    data = bot.data
    assert data is not None
    chat = _decision_makers(bot)[ChatReplies]
    gm = ChatLine(ChatKind.GM, np.zeros((16, 20, 3), np.uint8), "hi", 600)
    monkeypatch.setattr(data.chat_reader, "read", lambda frame: Reading.read([gm], 1.0))
    alarms: list[str] = []
    monkeypatch.setattr(chat, "emit", lambda event, *a, **k: alarms.append(event))
    assert bot.supervisor is not None

    asyncio.run(chat._decide())  # pyright: ignore[reportPrivateUsage]

    assert CHAT_GM_LINE in alarms
    paused = {
        c
        for c in bot._decision_makers()  # pyright: ignore[reportPrivateUsage]
        if any(p.holder == USER for p in bot.supervisor.held(c))
    }
    assert paused == set(bot._decision_makers()) - {ChatReplies}  # pyright: ignore[reportPrivateUsage]
