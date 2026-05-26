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
        still_in_map = self._perform_check()
        if not still_in_map:

            # Reset minimap attributes and move mouse away
            logger.log(LOG_LEVEL, "Suspected Not in map. Toggling minimap.")
            try:
                self._minimap_pos_error_handler()
            except :
                pass

            # Re-try
            if not self._perform_check():
                logger.critical("Confirmed Not in map. Pausing bot.")
                self._disable_decision_makers(
                    "Rotation",
                    "CheckStillInMap",
                    "CheckMobsStillSpawn",
                    "MobsHitting",
                    "PartyRebuff",
                )
                self._react("advanced")
                return

        if not still_in_map:
            # If we reach this point and there was an issue originally
            logger.log(LOG_LEVEL, "Problem solved, still in map.")

    def _perform_check(self) -> bool:
        try:
            return self.data.current_minimap.validate_in_map(self.data.handle)
        except FileNotFoundError as e:
            raise e
        except BaseException as e:
            return False