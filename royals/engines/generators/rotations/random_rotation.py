import logging
import math
import multiprocessing as mp
import time

from botting import PARENT_LOG
from botting.models_abstractions import Skill
from .base_rotation import Rotation
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class RandomRotation(Rotation):
    def __init__(
        self, data: RoyalsData, lock: mp.Lock = None, teleport: Skill = None
    ) -> None:
        super().__init__(data, lock, teleport)

    def __call__(self):
        self._next_target = self.data.current_minimap.random_point()
        self.data.update("current_minimap_position")
        return iter(self)

    def _set_next_target(self):
        if math.dist(self.data.current_minimap_position, self._next_target) > 2:
            pass
        else:
            self._next_target = self.data.current_minimap.random_point()

    def _single_iteration(self):
        res = None

        if self._prev_pos != self.data.current_minimap_position:
            self._last_pos_change = time.perf_counter()

        actions = get_to_target(
            self.data.current_minimap_position,
            self._next_target,
            self.data.current_minimap,
        )
        if actions:
            self._deadlock_counter = 0
            res = self._create_partial(actions[0])

            if self._lock is None:
                return res

            elif self._lock.acquire(block=False):
                logger.debug(f"Rotation Lock acquired. Sending Next Random Rotation.")
                return res
        else:
            self._deadlock_counter += 1

        return res
