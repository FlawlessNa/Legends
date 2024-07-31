import logging
import multiprocessing.connection
import multiprocessing.managers
from functools import partial

from botting import PARENT_LOG, controller
from botting.core import BotData, DecisionMaker
from royals.model.mechanics import get_to_target

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')
LOG_LEVEL = logging.NOTSET
DISTANCE_THRESHOLD = 10


class _NextTargetMixin:
    """
    Utility function to set next target.
    """
    def _converge_towards_mobs(self):
        """
        Sets the next target to a central point among the detected mobs in a given
        direction. # TODO -> Mimics the SmartRotationGenerator
        :return:
        """
        pass

    def _get_next_target_from_feature_cycle(self):
        """
        Sets the next target from the feature cycle.
        :return:
        """
        pass


class Rotation(DecisionMaker, _NextTargetMixin):
    def __init__(
            self,
            metadata: multiprocessing.managers.DictProxy,
            data: BotData,
            pipe: multiprocessing.connection.Connection,
            **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get('Teleport')

    async def _decide(self) -> None:
        logger.log(LOG_LEVEL, f"{self} is deciding.")

    def _compute_full_path(
        self, current: tuple[int, int], target: tuple[int, int]
    ) -> list[partial]:
        """
        Re-calculates the entire path
        """
        return get_to_target(
            current,
            target,
            self.data.current_minimap,
            self.data.handle,
            controller.key_binds(self.data.ign)["jump"],
            self._teleport_skill,
            self.data.ign
        )

    def _set_next_target(self):
        pass

    def _truncate_path(self, current, path):
        """
        Instead of re-calculating full path, use the existing path.
        Look at current position and compute the closest node that is on the path. Then,
        truncate path from that node onwards.
        """
        pass



