import asyncio
import logging
import math
import multiprocessing as mp
import numpy as np
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionGenerator
from botting.utilities import take_screenshot
from botting.models_abstractions import Skill, BaseMob
from royals import RoyalsData
from royals.actions import random_jump, teleport, telecast, cast_skill
from royals.models_implementations.mechanics.path_into_movements import get_to_target

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class TelecastRotation(DecisionGenerator):
    def __init__(
        self,
        data: RoyalsData,
        lock: mp.Lock,
        teleport_skill: Skill,
        ultimate: Skill,
        mob_threshold: int = 5,
    ) -> None:
        self.data = data
        self._lock = lock
        self._teleport = teleport_skill
        self._ultimate = ultimate
        self._mob_threshold = mob_threshold

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

    def _create_partial(self, action: callable) -> callable:
        args = (
            self.data.handle,
            self.data.ign,
            action.keywords.get("direction", self.data.current_direction),
        )
        kwargs = action.keywords
        kwargs.pop("direction", None)
        if action.func.__name__ == "teleport":
            kwargs.update(teleport_skill=self._teleport)
        return partial(action.func, *args, **kwargs)

    def _single_iteration(self):
        img = take_screenshot(self.data.handle, self.data.current_map.detection_box)
        mob_count = self.mob_count_in_img(img, self.data.current_mobs)

        if self._prev_pos != self.data.current_minimap_position:
            self._last_pos_change = time.perf_counter()

        actions = get_to_target(
            self.data.current_minimap_position,
            self._next_target,
            self.data.current_minimap,
        )
        if not actions:
            self._deadlock_counter += 1
        else:
            self._deadlock_counter = 0

            if mob_count < self._mob_threshold or self.data.character_in_a_ladder:
                res = self._create_partial(actions[0])

            else:
                # Sufficient mobs and not currently on a ladder
                if not actions[0].func.__name__ == 'teleport':
                    # If first movement isn't a teleport, simply cast skill instead
                    res = partial(
                        cast_skill, self.data.handle, self.data.ign, self._ultimate
                    )
                else:
                    # If first movement is a teleport, replace by telecast and keep teleporting

                    directions = []
                    while actions and actions[0].func.__name__ == "teleport":
                        next_action = actions.pop(0)
                        directions.append(
                            next_action.keywords.get(
                                "direction", self.data.current_direction
                            )
                        )
                    res = partial(self._full_telecast,
                                  self.data.handle,
                                  self.data.ign,
                                  self._teleport,
                                  self._ultimate,
                                  directions
                                  )

            if self._lock is None:
                return res
            elif self._lock.acquire(block=False):
                logger.debug(
                    f"Rotation Lock acquired. Sending Next Random Rotation."
                )
                return res

    @staticmethod
    async def _full_telecast(handle: int, ign: str, teleport_skill: Skill, ultimate_skill: Skill, directions: list[str]) -> None:
        async def _coro():
            direction = directions.pop(0)
            await telecast(
                handle, ign, direction, teleport_skill, ultimate_skill
            )
            while directions:
                direction = directions.pop(0)
                await teleport(
                    handle,
                    ign,
                    direction,
                    teleport_skill,
                )
        await asyncio.wait_for(_coro(), timeout=ultimate_skill.animation_time)

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

    @staticmethod
    def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob]) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found within that image.
        :param img: Potentially cropped image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img) for mob in mobs])
