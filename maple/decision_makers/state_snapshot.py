import logging
import multiprocessing.connection
import multiprocessing.managers
from collections.abc import Sequence
from typing import Any

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker
from maple.model.world import WorldMap
from maple.screen.position import marker_of_feet
from maple.telemetry_events import STATE_SNAPSHOT, state_snapshot_payload

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class StateSnapshot(DecisionMaker):
    """
    Once a second, records where the character is and where it is heading.

    Reads only what other DecisionMakers have already read
    (`get_last_known_value`, never an update), so it takes no screenshot and costs
    the bot nothing. A value nobody has read yet is recorded as null. Not part of
    any shipped Bot: a Profile adds it when a Session needs the trail.
    """

    _throttle = 1.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)

    def _last_known(self, name: str) -> Any:  # noqa: ANN401
        try:
            return self.data.get_last_known_value(name, update=False)
        except AttributeError:
            return None

    async def _decide(self) -> None:
        reading = self._last_known("current_position")
        value = getattr(reading, "value", None)
        position = None if value is None else (value.x, value.y)
        target = self._last_known("next_target")
        # The canvas fields, as they always were: where the minimap draws the
        # marker for the virtual position and target (#398).
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        transform = None if world_map is None else world_map.minimap

        def canvas(point: Sequence[float] | None) -> tuple[int, int] | None:
            if point is None or transform is None:
                return None
            return marker_of_feet(transform, (point[0], point[1]))

        self.emit(
            STATE_SNAPSHOT,
            state_snapshot_payload(
                canvas(position),
                canvas(target),
                self._last_known("current_on_screen_position"),
                virtual_position=position,
                virtual_target=target,
            ),
        )
