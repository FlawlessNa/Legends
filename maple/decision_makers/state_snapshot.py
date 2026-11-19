import logging
import multiprocessing.connection
import multiprocessing.managers
from collections.abc import Sequence

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker
from maple.screen.position import marker_of_feet
from maple.telemetry_events import STATE_SNAPSHOT, state_snapshot_payload

from .providers import DESTINATION, ON_SCREEN_POSITION, POSITION, WORLD_MAP

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class StateSnapshot(DecisionMaker):
    """
    Once a second, records where the character is and where it is heading.

    Only observes what other DecisionMakers have already read (`peek`, never a
    refresh), so it takes no screenshot, sends nothing, and costs the bot
    nothing. It reads no key, so it causes no Provider to be built: a value
    nobody has read yet, or whose Provider the Bot does not build, is recorded as
    null. Not part of any shipped Bot: a Profile adds it when a Session needs the
    trail.
    """

    observes = (POSITION, DESTINATION, ON_SCREEN_POSITION, WORLD_MAP)
    _throttle = 1.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)

    async def _decide(self) -> None:
        reading = self.peek(POSITION)
        value = None if reading is None else reading.value
        position = None if value is None else (value.x, value.y)
        target = self.peek(DESTINATION)
        # The canvas fields, as they always were: where the minimap draws the
        # marker for the virtual position and target (#398).
        world_map = self.peek(WORLD_MAP)
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
                self.peek(ON_SCREEN_POSITION),
                virtual_position=position,
                virtual_target=target,
            ),
        )
