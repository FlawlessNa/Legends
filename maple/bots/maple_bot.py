import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC
from collections.abc import Mapping
from typing import Any

from botting import PARENT_LOG, emit_event
from botting.core import Bot, ProxyFactory
from botting.screen import Frame, frame_source
from botting.visuals import InGameDetectionVisuals
from maple.actions import ensure_minimap_displayed, startup_chat_keys
from maple.bots.map_check import check_named_map, identify_map
from maple.bots.map_mobs import MapMob, check_detection, map_mobs
from maple.bots.map_setting import (
    is_auto,
    refuse_game_map,
    refuse_mobs,
    resolve_map_id,
)
from maple.bots.skill_settings import buff_names, refuse_buff_lists
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.decision_makers.providers import (
    CharacterProvider,
    ClientProvider,
    MapProvider,
    MobsProvider,
    ProfileProvider,
    ScreenReadersProvider,
    SkillsProvider,
)
from maple.decision_makers.rotation_setting import rotation_name
from maple.launchers.profile import ProfileError
from maple.model.characters import MAPPING as CHARACTER_MAPPING
from maple.model.characters import character_class as job_class
from maple.model.mechanics.physics import Calibration, game_physics
from maple.model.world import WorldMap
from maple.screen.buffs import ICON_BASE, BuffsReader
from maple.screen.chat import TARGET_SELECT, ChatReader
from maple.screen.client import find_client
from maple.screen.font import NAME_TAG
from maple.screen.locator import FrameCheck
from maple.screen.map_identification import MapCanvases, MapIdentifier
from maple.screen.minimap import MINIMAP, NW, MinimapReader
from maple.screen.minimap_title import MINIMAP_TITLE_READER, MinimapTitleReader
from maple.screen.position import PositionFusion
from maple.screen.quick_slots import QUICK_SLOTS, QuickSlotsReader
from maple.screen.sprites import (
    Profile,
    ReaderSprites,
    StartupRefused,
    enabled_readers,
    load_reader_sprites,
    with_readers,
)
from maple.screen.status_bar import BACKGROUND as STATUS_BAR_BACKGROUND
from maple.screen.status_bar import StatusBarReader
from maple.telemetry_events import CHAT_REPLIES_TOGGLED, RepliesToggledPayload

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MapleBot(Bot, ABC):
    """
    A Bot on the MapleStory client: it finds the client by its window class and
    executable, and takes its job from the profile's `character_class`.

    With a named `map`, or `map: auto`, it checks the minimap at start, before
    any reader attribute exists (`map_check`), and refuses to start on another
    map or on one it can't tell. Showing the minimap for that check may press
    the minimap key.

    The mobs its detection looks for are the map's, from its spawns in the
    game data (`map_mobs`), by detection class name (`current_mobs`). A bot
    that detects mobs refuses to start when no model in `models_path` detects
    one of them: a named map's before anything is pressed, `map: auto`'s once
    the map is identified.
    """

    def _replies_toggled(self, on: bool, source: str) -> None:
        payload: RepliesToggledPayload = {"on": on, "source": source}
        emit_event(None, CHAT_REPLIES_TOGGLED, payload, logger.name)

    MINIMAP_TIME_LIMIT = 7.5
    """Seconds the minimap key is pressed for at start to show the minimap, as
    `MinimapProvider.TIME_LIMIT`."""

    def __init__(
        self,
        ign: str,
        metadata: multiprocessing.managers.DictProxy,
        map: str | int | None = None,
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
        refuse_mobs(kwargs.pop("mobs", None))
        refuse_buff_lists(
            kwargs.pop("included_buffs", None), kwargs.pop("excluded_buffs", None)
        )
        #: The buffs `SoloRebuff` keeps up, by skill name: the profile's `buffs`.
        self.buffs: tuple[str, ...] = buff_names(kwargs.get("buffs"))
        # Read here, in Main Process, so a bad `rotation` ends the launch with
        # one line; the Destination Provider reads it again, to the same answer.
        #: The rotation the profile names (`rotation_name`): a Bot decides which
        #: DecisionMakers it runs by it.
        self.rotation: str = rotation_name(kwargs)
        super().__init__(ign, metadata, **kwargs)
        # Read once, here: a malformed `Chat Keys` refuses the start, rather than
        # after a failsafe reaction or a Discord WRITE. DecisionMakers take them
        # from `data.chat_keys`, the Discord parser from `started_chat_keys`.
        try:
            self.chat_keys = startup_chat_keys(ign)
        except (TypeError, ValueError) as exc:
            message = f"Refusing to start {ign}: {exc}"
            logger.critical(message)
            raise StartupRefused(message) from exc
        if not character_class:
            raise ValueError(
                f"{type(self).__name__} for {ign!r} needs `character_class` in the "
                "profile's settings, one of: " + ", ".join(sorted(CHARACTER_MAPPING))
            )
        try:
            self.job, self.character_class = job_class(character_class)
        except LookupError as error:
            raise ProfileError(
                f"`character_class: {character_class}`: {error}"
            ) from error
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.models_path = models_path
        self.map_id = resolve_map_id(map)
        self.map_auto = is_auto(map)
        # The map's mobs, once it is known: a named map's here, so a map no
        # model covers is refused before the minimap key is pressed.
        self.mobs: tuple[MapMob, ...] = ()
        if self.map_id is not None and self._detects_mobs():
            self.mobs = self._map_mobs(self.map_id)
        # Parsed here so a misspelt constant refuses the start; Movement Plans
        # read it as `CALIBRATION` (`ProfileProvider`).
        self.calibration = Calibration.from_mapping(calibration)
        self.kwargs = kwargs
        self.kwargs.update(ign=ign)

    def find_handle(self) -> int:
        return find_client()

    def _detects_mobs(self) -> bool:
        """Whether a Decision Maker of this bot detects mobs, and so needs a
        model for the map's."""
        return MobsHitting in self._decision_makers()

    def _map_mobs(self, map_id: int) -> tuple[MapMob, ...]:
        """
        The mobs map `map_id` has (`map_mobs`), once checked against the
        profile's models.

        :raises ProfileError: No model in `models_path` detects one of them
            (`check_detection`).
        """
        world_map = WorldMap.load(map_id)
        mobs = map_mobs(world_map.mobs)
        label = f"map {map_id}" + (f" ({world_map.name})" if world_map.name else "")
        check_detection(mobs, self.models_path, label)
        if not mobs:
            logger.warning(
                "%s has no mobs: %s for %r detects none, so it never casts.",
                label,
                type(self).__name__,
                self.ign,
            )
        return mobs

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: threading.Barrier,
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.

        Loads the readers' sprites, checks the map on the minimap, then builds
        the Bot-level Providers with what it found, in this order: the screen
        readers, the map, the character, the map's mobs, and the client's frame
        and chat keys, and the profile's movement stats
        (`maple.decision_makers.providers`). DecisionMakers read them as keys.
        """
        super().child_init(pipe, barrier)
        assert self.data is not None
        if self.models_path is None and self._detects_mobs():
            # Mob and character detection are what read a model; a bot that
            # detects neither (a calibration sitting) needs no `models_path`.
            raise ValueError(
                f"{type(self).__name__} for {self.ign!r} hits mobs, which needs "
                "`models_path` in the profile's settings (see profiles/example.yaml)."
            )
        data = self.data
        providers = data.providers
        assert providers is not None, "Bot.child_init makes them"
        # The readers' sprites are loaded once, before any reader exists: a
        # missing or stale store refuses the start here, not mid-cycle.
        map_id = self.map_id
        readers = with_readers(
            enabled_readers(self._decision_makers()),
            MINIMAP,
            *((MINIMAP_TITLE_READER,) if self.map_auto else ()),
        )
        profile = Profile(job=self.job, map_id=map_id, buffs=self.buffs)
        reader_sprites = load_reader_sprites(readers, profile)
        map_id, reader_sprites = self._check_map_at_start(reader_sprites)
        if self.map_auto and self._detects_mobs():
            self.mobs = self._map_mobs(map_id)
        screen: dict[str, object] = {}
        world: dict[str, object] = {}
        if reader_sprites.build is not None:
            frame_check = FrameCheck(reader_sprites)
            screen["frame_check"] = frame_check
            if map_id is not None:
                world = self._world_map(map_id, frame_check)
            if STATUS_BAR_BACKGROUND in reader_sprites.canvases:
                screen["status_bar"] = StatusBarReader(reader_sprites, frame_check)
            if QUICK_SLOTS in readers:
                screen["quick_slots"] = QuickSlotsReader(reader_sprites, frame_check)
            if ICON_BASE in reader_sprites.canvases:
                screen["buffs"] = BuffsReader(reader_sprites, frame_check)
            if NW in reader_sprites.canvases:
                screen["minimap"] = MinimapReader(
                    reader_sprites, frame_check, map_id=map_id
                )
            if TARGET_SELECT in reader_sprites.canvases:
                screen["chat"] = ChatReader(reader_sprites, frame_check, ign=self.ign)
        providers.add(ScreenReadersProvider, sprites=reader_sprites, **screen)
        providers.add(MapProvider, map_id=map_id, **world)
        InGameDetectionVisuals.register_models(self.models_path)
        InGameDetectionVisuals.register_cache_id(data.handle)
        providers.add(
            CharacterProvider,
            character_class=self.character_class,
            detection_configs=self.detection_configs,
            client_size=self.client_size,
            name_tags=reader_sprites.glyph_sets.get(NAME_TAG.name),
            buff_names=profile.buffs,
        )
        providers.add(SkillsProvider, job=self.job)
        providers.add(
            MobsProvider,
            detection_classes=[
                mob.detection_class
                for mob in self.mobs
                if mob.detection_class is not None
            ],
        )
        # The bot's one capture: the readers take the `Frame`, mob and
        # character detection its pixels.
        providers.add(ClientProvider, chat_keys=self.chat_keys)
        # The character's speed and jump stats, from the profile. A Bot that
        # builds the ability menu's Provider (`AbilityPointDistributor`) reads
        # them off the menu too; Movement Plans take those when they exist
        # (`PathingProvider.physics`), and these otherwise.
        providers.add(ProfileProvider, calibration=self.calibration)

    def _world_map(self, map_id: int, frame_check: FrameCheck) -> dict[str, object]:
        """
        `MapProvider`'s values for map `map_id`: `world_map`, the map's
        `WorldMap` from the game data store the readers' sprites came from,
        `game_physics`, the store's `Physics.img` values Movement Plans derive
        their physics from, and `position_fusion`, the reader of the position on
        it, unless the map has no minimap. Nothing is drawn or indexed here: the
        static render is, on the first position read.

        :raises LookupError: The store's catalogue has no map `map_id`.
        """
        world_map = WorldMap.load(map_id)
        world: dict[str, object] = {
            "world_map": world_map,
            "game_physics": game_physics(),
        }
        if world_map.minimap is None:
            logger.warning("Map %d has no minimap: no position is read.", map_id)
            return world
        world["position_fusion"] = PositionFusion.for_map(world_map, frame_check)
        return world

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
