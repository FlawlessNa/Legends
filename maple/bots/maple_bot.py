import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC
from collections.abc import Mapping, Sequence
from typing import Any

from botting import PARENT_LOG
from botting.core import Bot, ProxyFactory
from botting.screen import Frame, frame_source
from botting.visuals import InGameDetectionVisuals
from maple.actions import ensure_minimap_displayed
from maple.bots.map_check import check_named_map, identify_map
from maple.bots.map_setting import is_auto, refuse_game_map, resolve_map_id
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.decision_makers.rebuffs import solo_buffs
from maple.launchers.profile import ProfileError
from maple.model.characters import MAPPING as CHARACTER_MAPPING
from maple.model.mechanics.maple_mob import MapleMob
from maple.model.mechanics.physics import Calibration, game_physics
from maple.model.world import WorldMap
from maple.screen.buffs import ICON_BASE, BuffsReader
from maple.screen.chat import TARGET_SELECT, ChatReader
from maple.screen.client import find_client
from maple.screen.locator import FrameCheck
from maple.screen.map_identification import MapCanvases, MapIdentifier
from maple.screen.minimap import MINIMAP, NW, MinimapReader
from maple.screen.minimap_title import MINIMAP_TITLE_READER, MinimapTitleReader
from maple.screen.position import PositionFusion
from maple.screen.quick_slots import QUICK_SLOTS, QuickSlotsReader
from maple.screen.sprites import (
    Profile,
    ReaderSprites,
    enabled_readers,
    load_reader_sprites,
    with_readers,
)
from maple.screen.status_bar import BACKGROUND as STATUS_BAR_BACKGROUND
from maple.screen.status_bar import StatusBarReader

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MapleBot(Bot, ABC):
    """
    A Bot on the MapleStory client: it finds the client by its window class and
    executable, and takes its job from the profile's `character_class`.

    With a named `map`, or `map: auto`, it checks the minimap at start, before
    any reader attribute exists (`map_check`), and refuses to start on another
    map or on one it can't tell. Showing the minimap for that check may press
    the minimap key.

    The mobs its detection looks for are the profile's `mobs`, by detection
    class name (`current_mobs`); none when the profile names none.
    """

    MINIMAP_TIME_LIMIT = 7.5
    """Seconds the minimap key is pressed for at start to show the minimap, as
    `MinimapAttributesMixin.ERROR_HANDLING_TIME_LIMIT`."""

    def __init__(
        self,
        ign: str,
        metadata: multiprocessing.managers.DictProxy,
        map: str | int | None = None,
        mobs: Sequence[str] | None = None,
        detection_configs: str | None = None,
        client_size: str = "medium",
        models_path: dict[str, str] | None = None,
        character_class: str | None = None,
        calibration: Mapping[str, object] | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        # A retired setting refuses the start rather than landing in `kwargs`
        # unread.
        refuse_game_map(kwargs.pop("game_map", None))
        super().__init__(ign, metadata, **kwargs)
        if not character_class:
            raise ValueError(
                f"{type(self).__name__} for {ign!r} needs `character_class` in the "
                "profile's settings, one of: " + ", ".join(sorted(CHARACTER_MAPPING))
            )
        self.job = character_class.title()
        self.character_class = CHARACTER_MAPPING[self.job]
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.models_path = models_path
        self.map_id = resolve_map_id(map)
        self.map_auto = is_auto(map)
        if isinstance(mobs, str):
            raise ProfileError(
                f"`mobs: {mobs}` must be a list of mob names, such as `[{mobs}]`."
            )
        self.mobs = tuple(mobs or ())
        if not self.mobs and MobsHitting in self._decision_makers():
            # `MobsHitting` counts 0 mobs every cycle and the bot never casts.
            # An empty list stays valid for a bot that does not train.
            logger.warning(
                "Profile %r has no `mobs`: this bot hits mobs, but its detection "
                "looks for none, so it will never cast. Add `mobs: [...]` to "
                "the profile's settings.",
                ign,
            )
        # Parsed here so a misspelt constant refuses the start; Movement Plans
        # read it through `data.calibration`.
        self.calibration = Calibration.from_mapping(calibration)
        self.kwargs = kwargs
        self.kwargs.update(ign=ign)

    def find_handle(self) -> int:
        return find_client()

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: threading.Barrier,
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        Since virtually every bot will at some point require to know the character class
        and be made aware of the minimap position, those attributes are created here for
        convenience.
        """
        super().child_init(pipe, barrier)
        # `Bot.child_init` is what builds `self.data`; everything below reads it,
        # including the lambdas, which a narrowing assert alone would not reach.
        assert self.data is not None
        if self.models_path is None and MobsHitting in self._decision_makers():
            # Mob and character detection are what read a model; a bot that
            # detects neither (a calibration sitting) needs no `models_path`.
            raise ValueError(
                f"{type(self).__name__} for {self.ign!r} hits mobs, which needs "
                "`models_path` in the profile's settings (see profiles/example.yaml)."
            )
        data = self.data
        # The readers' sprites are loaded once, before any reader attribute
        # exists: a missing or stale store refuses the start here, not mid-cycle.
        map_id = self.map_id
        readers = with_readers(
            enabled_readers(self._decision_makers()),
            MINIMAP,
            *((MINIMAP_TITLE_READER,) if self.map_auto else ()),
        )
        profile = Profile(
            job=self.job,
            map_id=map_id,
            buffs=tuple(
                buff.name
                for buff in solo_buffs(
                    self.character_class.skills,
                    self.kwargs.get("included_buffs"),
                    self.kwargs.get("excluded_buffs"),
                )
            ),
        )
        reader_sprites = load_reader_sprites(readers, profile)
        map_id, reader_sprites = self._check_map_at_start(reader_sprites)
        data.set_static("map_id", map_id)
        data.set_static("reader_sprites", reader_sprites)
        data.set_static("buff_names", profile.buffs)
        data.set_static("world_map", None)
        data.set_static("game_physics", None)
        data.set_static("position_fusion", None)
        if reader_sprites.build is not None:
            frame_check = FrameCheck(reader_sprites)
            data.set_static("frame_check", frame_check)
            if map_id is not None:
                self._set_world_map(map_id, frame_check)
            if STATUS_BAR_BACKGROUND in reader_sprites.canvases:
                data.set_static(
                    "status_bar_reader", StatusBarReader(reader_sprites, frame_check)
                )
            if QUICK_SLOTS in readers:
                data.set_static(
                    "quick_slots_reader", QuickSlotsReader(reader_sprites, frame_check)
                )
            if ICON_BASE in reader_sprites.canvases:
                data.set_static(
                    "buffs_reader", BuffsReader(reader_sprites, frame_check)
                )
            if NW in reader_sprites.canvases:
                data.set_static(
                    "minimap_reader",
                    MinimapReader(reader_sprites, frame_check, map_id=map_id),
                )
            if TARGET_SELECT in reader_sprites.canvases:
                data.set_static("chat_reader", ChatReader(reader_sprites, frame_check))
        InGameDetectionVisuals.register_models(self.models_path)
        InGameDetectionVisuals.register_cache_id(data.handle)
        data.create_attribute(
            "character",
            lambda: self.character_class(
                self.ign, self.detection_configs, self.client_size
            ),
        )
        data.create_attribute(
            "current_mobs", lambda: tuple(MapleMob(name) for name in self.mobs)
        )
        # The bot's one capture: the readers take the `Frame`, mob and
        # character detection its pixels. `update_attribute("current_frame")`
        # captures a fresh one.
        data.create_attribute(
            "current_frame", lambda: frame_source().grab(data.handle), threshold=0.1
        )
        # The character's current speed and jump stats, from the profile at the
        # start of a Session. A later reading replaces them (the ability menu's
        # today, #314's stat window reader next); Movement Plans read them each
        # time they plan, so the next Path follows the new values.
        data.set_static("speed_multiplier", self.kwargs.get("speed_multiplier", 1.00))
        data.set_static("jump_multiplier", self.kwargs.get("jump_multiplier", 1.00))
        data.set_static("calibration", self.calibration)

    def _set_world_map(self, map_id: int, frame_check: FrameCheck) -> None:
        """
        Publishes `world_map`, the map's `WorldMap` from the game data store
        the readers' sprites came from, `game_physics`, the store's
        `Physics.img` values Movement Plans derive their physics from, and
        `position_fusion`, the reader of `current_position` on it. Nothing is
        drawn or indexed here: the static render is, on the first position
        read.

        :raises LookupError: The store's catalogue has no map `map_id`.
        """
        assert self.data is not None
        world_map = WorldMap.load(map_id)
        self.data.set_static("world_map", world_map)
        self.data.set_static("game_physics", game_physics())
        if world_map.minimap is None:
            logger.warning("Map %d has no minimap: no position is read.", map_id)
            return
        self.data.set_static(
            "position_fusion", PositionFusion.for_map(world_map, frame_check)
        )

    def _check_map_at_start(self, sprites: ReaderSprites) -> tuple[int, ReaderSprites]:
        """
        The on-screen map check (`map_check`): shows the minimap, with its
        banner for `map: auto`, then checks the named map or identifies it.

        :returns: The map's id, and `sprites` with its minimap canvas, which
            `map: auto` couldn't declare before the map was known.
        :raises StartupRefused: The minimap shows another map than the named
            one, or the map can't be told.
        """
        assert self.data is not None
        handle = self.data.handle
        minimap = MinimapReader(sprites, FrameCheck(sprites), map_id=self.map_id)
        self._show_minimap(minimap, banner=self.map_auto)

        def grab() -> Frame:
            return frame_source().grab(handle)

        if not self.map_auto:
            map_id = self.map_id
            assert map_id is not None
            check_named_map(
                lambda: minimap.is_expected_map(grab(), map_id), f"map {map_id}"
            )
            return map_id, sprites
        canvases = MapCanvases.load()
        title = MinimapTitleReader(sprites, minimap, canvases.titles)
        identifier = MapIdentifier(minimap, title, canvases)
        reading = identify_map(lambda: identifier.identify(grab()))
        assert reading.value is not None
        found = canvases[reading.value]
        logger.info(
            "map: auto identified %s (%d): %s",
            found.title,
            found.map_id,
            reading.detail,
        )
        return found.map_id, sprites.with_canvas(found.canvas)

    def _show_minimap(self, minimap: MinimapReader, *, banner: bool) -> None:
        """
        Presses the minimap key until the minimap is expanded, with its banner
        when `banner`. When the banner can't be shown, any expanded look will
        do, since the canvas match can still tell the map; when even that
        fails, the check that follows reads the minimap as it is, and refuses.
        """
        assert self.data is not None
        assert self.pipe is not None
        identifier = f"{type(self).__name__}({self.ign}) map check at start"
        condition = ProxyFactory(self.metadata).instance(identifier, "Condition")
        for with_banner in (True, False) if banner else (False,):
            try:
                ensure_minimap_displayed(
                    identifier,
                    self.data.handle,
                    self.ign,
                    self.pipe,
                    minimap,
                    condition,
                    self.MINIMAP_TIME_LIMIT,
                    banner=with_banner,
                )
                return
            except TimeoutError as error:
                logger.warning(
                    "The minimap couldn't be shown expanded%s at start: %s",
                    " with its banner" if with_banner else "",
                    error,
                )
