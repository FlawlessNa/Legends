import logging
import multiprocessing.connection
import multiprocessing.managers
from collections.abc import Sequence
from typing import Any

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker
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

    def _last_known(self, name: str) -> Sequence[Any] | None:
        try:
            return self.data.get_last_known_value(name, update=False)
        except AttributeError:
            return None

    async def _decide(self) -> None:
        self.emit(
            STATE_SNAPSHOT,
            state_snapshot_payload(
                self._last_known("current_minimap_position"),
                self._last_known("next_target"),
                self._last_known("current_on_screen_position"),
            ),
        )
