import asyncio
import itertools
import logging
import math
import multiprocessing as mp
import numpy as np
import time

from functools import partial

from botting import PARENT_LOG
from botting.utilities import take_screenshot
from botting.models_abstractions import Skill, BaseMob
from .base_rotation import Rotation
from royals import RoyalsData
from royals.actions import teleport, telecast, cast_skill
from royals.models_implementations.mechanics.path_into_movements import get_to_target

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class TelecastRotation(Rotation):
    def __init__(
        self,
        data: RoyalsData,
        lock: mp.Lock,
        teleport_skill: Skill,
        ultimate: Skill,
        mob_threshold: int = 5,
    ) -> None:
        super().__init__(data, lock, teleport_skill)
        self._ultimate = ultimate
        self._mob_threshold = mob_threshold
        self._feature_generator = None

    def __call__(self):
        self.data.update(
            next_target=self.data.current_minimap.random_point(),
            last_cast=time.perf_counter(),
            ultimate=self._ultimate,
        )
        self._next_target = self.data.next_target
        self._last_pos_change = time.perf_counter()
        if len(self.data.current_minimap.feature_cycle):
            self._feature_generator = itertools.cycle(
                self.data.current_minimap.feature_cycle
            )
        return iter(self)

    def _set_next_target(self):
        if math.dist(self.data.current_minimap_position, self._next_target) > 2:
            pass
        else:
            if len(self.data.current_minimap.feature_cycle):
                self.data.update(next_target=next(self._feature_generator).random())
            else:
                self.data.update(next_target=self.data.current_minimap.random_point())
        self._next_target = self.data.next_target

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
                self.data.update(last_cast=time.perf_counter())
                # Sufficient mobs and not currently on a ladder
                if not actions[0].func.__name__ == "teleport":
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
                    res = partial(
                        self._full_telecast,
                        self.data.handle,
                        self.data.ign,
                        self._teleport,
                        self._ultimate,
                        directions,
                    )

            if self._lock is None:
                return res
            elif self._lock.acquire(block=False):
                logger.debug(f"Rotation Lock acquired. Sending Next Random Rotation.")
                return res

    @staticmethod
    async def _full_telecast(
        handle: int,
        ign: str,
        teleport_skill: Skill,
        ultimate_skill: Skill,
        directions: list[str],
    ) -> None:
        async def _coro():
            direction = directions.pop(0)
            await telecast(handle, ign, direction, teleport_skill, ultimate_skill)
            while directions:
                direction = directions.pop(0)
                await teleport(
                    handle,
                    ign,
                    direction,
                    teleport_skill,
                )

        await asyncio.wait_for(_coro(), timeout=ultimate_skill.animation_time)

    @staticmethod
    def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob]) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found within that image.
        :param img: Potentially cropped image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img) for mob in mobs])
