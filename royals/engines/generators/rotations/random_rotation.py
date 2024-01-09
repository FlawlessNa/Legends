import logging
import math
import multiprocessing as mp
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionGenerator
from botting.models_abstractions import Skill
from royals import RoyalsData
from royals.actions import random_jump
from royals.models_implementations.mechanics.path_into_movements import get_to_target

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class RandomRotation(DecisionGenerator):
    def __init__(
        self, data: RoyalsData, lock: mp.Lock = None, teleport: Skill = None
    ) -> None:
        self.data = data
        self._lock = lock
        self._teleport = teleport

    def __call__(self):
        self._next_target = self.data.current_minimap.random_point()
        self._last_pos_change = time.perf_counter()
        return iter(self)

    def __next__(self):
        self._prev_pos = self.data.current_minimap_position
        self.data.update("current_minimap_position")

        self._set_next_target()
        res = self._single_iteration()

        if self._failsafe():
            return QueueAction(
                identifier=f"FAILSAFE - {self.__class__.__name__}",
                priority=1,
                action=partial(random_jump, self.data.handle, self.data.ign),
                is_cancellable=False,
                release_lock_on_callback=True,
            )

        elif res:
            return QueueAction(
                identifier=self.__class__.__name__,
                priority=99,
                action=res,
                is_cancellable=True,
                release_lock_on_callback=True,
            )

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
            first_action = actions[0]
            args = (
                self.data.handle,
                self.data.ign,
                first_action.keywords.get("direction", self.data.current_direction),
            )
            kwargs = first_action.keywords
            kwargs.pop("direction", None)
            if first_action.func.__name__ == "teleport":
                kwargs.update(teleport_skill=self._teleport)

            if self._lock is None:
                res = partial(first_action.func, *args, **kwargs)

            elif self._lock.acquire(block=False):
                logger.debug(f"Rotation Lock acquired. Sending Next Random Rotation.")
                res = partial(first_action.func, *args, **kwargs)
        else:
            self._deadlock_counter += 1

        return res

    def _failsafe(self) -> callable:
        # If no change in position for 15 seconds, trigger failsafe
        if time.perf_counter() - self._last_pos_change > 15:
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to static position"
            )
            self._last_pos_change = time.perf_counter()
            return True

        elif self._deadlock_counter > 30:
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to no path found"
            )
            self._deadlock_counter = 0
            return True

        return False
