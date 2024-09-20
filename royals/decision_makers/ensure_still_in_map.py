import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG
from botting.core import BotData, DecisionMaker
from .mixins import (
    MinimapAttributesMixin,
    ReactionsMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class CheckStillInMap(MinimapAttributesMixin, ReactionsMixin, DecisionMaker):
    _throttle = 3.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        if not self.data.has_minimap_attributes:
            self._create_minimap_attributes()

    async def _decide(self) -> None:
        if not self.data.current_minimap.validate_in_map(self.data.handle):

            # Reset minimap attributes and move mouse away
            logger.log(LOG_LEVEL, "Suspected Not in map. Toggling minimap.")
            self._minimap_pos_error_handler()

            # Re-try
            if not self.data.current_minimap.validate_in_map(self.data.handle):
                logger.critical("Confirmed Not in map. Pausing bot.")
                self._disable_decision_makers(
                    "Rotation",
                    "CheckStillInMap",
                    "CheckMobsStillSpawn",
                    "MobsHitting",
                    "PartyRebuff",
                )
                self._react("advanced")
