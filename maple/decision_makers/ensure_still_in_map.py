import contextlib
import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker
from maple.model.world import WorldMap
from maple.screen.minimap import MinimapState
from maple.telemetry_events import (
    RECOVERY_MAP_CHECK_FAILED,
    RECOVERY_MAP_CHECK_RECOVERED,
    MapCheckPayload,
)

from .mixins import (
    MinimapAttributesMixin,
    ReactionsMixin,
)

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


class CheckStillInMap(MinimapAttributesMixin, ReactionsMixin, DecisionMaker):
    _throttle = 3.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        if not self.data.has_minimap_attributes:
            self._create_minimap_attributes()
        self.map_name = map_title(self.data.world_map)

    async def _decide(self) -> None:
        still_in_map = self._perform_check()
        if not still_in_map:
            # Reset minimap attributes and move mouse away
            checked: MapCheckPayload = {"map_name": self.map_name}
            self.emit(RECOVERY_MAP_CHECK_FAILED, checked)
            with contextlib.suppress(BaseException):
                self._minimap_pos_error_handler()

            # Re-try
            if not self._perform_check():
                logger.critical("Confirmed Not in map. Pausing bot.")
                self._disable_decision_makers(
                    "Rotation",
                    "CheckStillInMap",
                    "CheckMobsStillSpawn",
                    "MobsHitting",
                )
                self._react("advanced")
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
        self.data.update_attribute("current_frame")
        frame = self.data.current_frame
        reader = self.data.minimap_reader
        world_map: WorldMap | None = self.data.world_map
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
