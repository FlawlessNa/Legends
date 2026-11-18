import contextlib
import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker, StartupRefused
from maple.model.world import WorldMap
from maple.screen.minimap import MINIMAP, MinimapState
from maple.telemetry_events import (
    RECOVERY_MAP_CHECK_FAILED,
    RECOVERY_MAP_CHECK_RECOVERED,
    MapCheckPayload,
)

from .ensure_mob_still_spawn import CheckMobsStillSpawn
from .mobs_hitting import MobsHitting
from .providers import FRAME, MINIMAP_READER, WORLD_MAP, MinimapRecovery
from .reactions import Reactions
from .rotation import Rotation

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


def map_title(world_map: WorldMap | None) -> str:
    """
    The map as the client names it, "street: name" as a profile names it; its
    ID when the client names it nowhere, and "an unknown map" with no map.
    """
    if world_map is None:
        return "an unknown map"
    if world_map.name is None:
        return str(world_map.id)
    if world_map.street is None:
        return world_map.name
    return f"{world_map.street}: {world_map.name}"


class CheckStillInMap(DecisionMaker):
    """
    Checks, every 3 s, that the bot is still on its map, on the minimap.

    When the check fails, it makes the minimap readable again (its
    `MinimapRecovery`) and checks once more. When that fails too, the bot is
    off its map: it stops the DecisionMakers that would act on the wrong map,
    itself included, until the user sends Discord `RESUME`, and reacts in the
    chat as a player would.
    """

    _throttle = 3.0
    screen_readers = (MINIMAP,)
    reads = (WORLD_MAP, *MinimapRecovery.reads, *Reactions.reads)
    pauses = (
        Rotation,
        "maple.decision_makers.ensure_still_in_map.CheckStillInMap",
        CheckMobsStillSpawn,
        MobsHitting,
    )

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._recovery = MinimapRecovery(self, self._proxies)
        self._reactions = Reactions(self, self)
        #: The map it checks, named for the telemetry. Read by `setup()`.
        self.map_name = map_title(None)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no minimap reader to check with.
        """
        if self.read(MINIMAP_READER) is None:
            raise StartupRefused(f"{self} checks the minimap, and has no reader.")
        self.map_name = map_title(self.read(WORLD_MAP))

    async def _decide(self) -> None:
        still_in_map = self._perform_check()
        if not still_in_map:
            # Reset minimap attributes and move mouse away
            checked: MapCheckPayload = {"map_name": self.map_name}
            self.emit(RECOVERY_MAP_CHECK_FAILED, checked)
            with contextlib.suppress(BaseException):
                self._recovery()

            # Re-try
            if not self._perform_check():
                logger.critical("Confirmed Not in map. Pausing bot.")
                self.pause_for_user(
                    Rotation,
                    CheckStillInMap,
                    CheckMobsStillSpawn,
                    MobsHitting,
                    reason=f"not on {self.map_name}",
                )
                self._reactions.react("advanced")
                return

        if not still_in_map:
            # If we reach this point and there was an issue originally
            recovered: MapCheckPayload = {"map_name": self.map_name}
            self.emit(RECOVERY_MAP_CHECK_RECOVERED, recovered)

    def _perform_check(self) -> bool:
        """
        Whether the bot is still in its map: the minimap shows the map's own
        `miniMap` canvas when the bot's `WorldMap` is known, or, without one, the
        minimap is shown expanded. Anything but a reading that says so counts as
        not in the map, which the caller retries once after recovering.
        """
        frame = self.refresh(FRAME)
        reader = self.read(MINIMAP_READER)
        assert reader is not None, "setup() refuses a Bot without one"
        world_map = self.read(WORLD_MAP)
        map_id = None if world_map is None else world_map.id
        if map_id is None:
            reading = reader.read(frame)
            in_map = (
                reading.value is not None
                and reading.value.state is MinimapState.EXPANDED
            )
        else:
            reading = reader.is_expected_map(frame, map_id)
            in_map = reading.value is True
        if not in_map:
            logger.debug(
                "%s map check: %s %s",
                self.data.ign,
                reading.status.value,
                reading.detail,
            )
        return in_map
