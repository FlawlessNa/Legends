import logging
import time

from abc import ABC, abstractmethod
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction
from botting.models_abstractions import Skill
from royals import RoyalsData
from royals.actions import random_jump


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class Rotation(DecisionGenerator, ABC):
    """
    Base class for all rotations, where a few helper methods are defined.
    """
    def __init__(self, data: RoyalsData, lock, teleport: Skill = None) -> None:
        self.data = data
        self._lock = lock
        self._teleport = teleport
        self._deadlock_counter = 0
        self._prev_pos = None
        self._last_pos_change = time.perf_counter()

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

    @abstractmethod
    def _set_next_target(self):
        pass

    @abstractmethod
    def _single_iteration(self):
        pass

    def _create_partial(self, action: callable) -> callable:
        args = (
            self.data.handle,
            self.data.ign,
            action.keywords.get("direction", self.data.current_direction),
        )
        kwargs = action.keywords.copy()
        kwargs.pop("direction", None)
        if action.func.__name__ == "teleport":
            kwargs.update(teleport_skill=self._teleport)
        return partial(action.func, *args, **kwargs)

    def _failsafe(self) -> callable:
        # If no change in position for 5 seconds, trigger failsafe
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
