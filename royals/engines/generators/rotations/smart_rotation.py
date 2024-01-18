import cv2
import itertools
import logging
import math
import multiprocessing as mp
import random
import time
from functools import partial

from botting import PARENT_LOG

from botting.models_abstractions import Skill
from botting.utilities import Box, take_screenshot
from royals.engines.generators.base_rotation import Rotation
from royals.game_data import RotationData
from royals.models_implementations.mechanics.path_into_movements import get_to_target


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class SmartRotation(Rotation):
    def __init__(
        self,
        data: RotationData,
        lock: mp.Lock,
        training_skill: Skill,
        mob_threshold: int,
        teleport: Skill = None,
        time_limit: float = 2,
    ) -> None:
        super().__init__(data, lock, training_skill, mob_threshold, teleport)
        self.time_limit = time_limit
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)

        self._next_feature_covered = []  # Used for rotation
        self._last_target_reached_at = time.perf_counter()
        self._first_time_on_target = True

        self._on_central_target = False  # Impacts rotation behavior
        self._cancellable = True  # Impacts rotation behavior

        if len(self.data.current_minimap.feature_cycle) > 0:
            self.data.update(
                next_feature=random.choice(self.data.current_minimap.feature_cycle)
            )
            self.data.update(next_target=self.data.next_feature.random())
            for _ in range(
                self.data.current_minimap.feature_cycle.index(self.data.next_feature)
                + 1
            ):
                next(self._target_cycle)
        else:
            self.data.update(next_target=self.data.current_minimap.random_point())
            self.data.update(
                next_feature=self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                )
            )
        self.data.update(allow_teleport=True if teleport is not None else False)

    @property
    def data_requirements(self) -> tuple:
        all_ = tuple(
            [
                "current_minimap_area_box",
                "current_entire_minimap_box",
                "minimap_grid",
                "current_minimap_position",
                "last_mob_detection",
                *super().data_requirements,
            ]
        )
        seen = set()
        return tuple(x for x in all_ if not (x in seen or seen.add(x)))

    def _set_next_target(self) -> None:
        """
        This is the method that determines the next target to move towards.
        Use current on-screen location to get a wide view on the current platform.
        If there are mobs, target the "average" position of those in the direction
        where there are most.
        :return:
        """
        dist = 2
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target) > dist
            or self.data.current_minimap_feature != self.data.next_feature
        ):
            self._first_time_on_target = True
            return

        # If we're on target, check if we've been on target for > time_limit seconds.
        if self._first_time_on_target:
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return
        elif time.perf_counter() - self._last_target_reached_at < self.time_limit:
            return

        # Reach this code once you've been on target for > time_limit seconds.
        self._first_time_on_target = True
        if self._on_screen_pos is not None:
            x, y = self._on_screen_pos
            region = Box(
                left=max(0, x - 500),
                right=min(1024, x + 500),
                top=max(0, y - 100),
                bottom=min(768, y + 100),
            )
            cropped_img = take_screenshot(self.data.handle, region)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if len(mobs_locations) >= self.mob_threshold:
                center_x = [rect[0] + rect[2] / 2 for rect in mobs_locations]
                left_x = [rect_x for rect_x in center_x if rect_x < x]
                right_x = [rect_x for rect_x in center_x if rect_x >= x]
                if len(left_x) > len(right_x):
                    avg_dist = sum([abs(rect_x - x) for rect_x in left_x]) / len(left_x)
                    minimap_dist = min(
                        int(avg_dist / 150 * 9), 9
                    )  # TODO - Make this dynamic
                    minimap_x, minimap_y = self.data.current_minimap_position
                    minimum_x = self.data.current_minimap_feature.left
                    target = (max(minimap_x - minimap_dist, minimum_x), minimap_y)
                    self.data.update(next_target=target)
                else:
                    avg_dist = sum([abs(rect_x - x) for rect_x in right_x]) / len(
                        right_x
                    )
                    minimap_dist = min(int(avg_dist / 150 * 9), 9)
                    minimap_x, minimap_y = self.data.current_minimap_position
                    maximum_x = self.data.current_minimap_feature.right
                    target = (min(minimap_x + minimap_dist, maximum_x), minimap_y)
                    self.data.update(next_target=target)

                return

        # If we reach this point, means there aren't enough mobs. Get to next feature.
        if len(self.data.current_minimap.feature_cycle) > 0:
            self.data.update(next_feature=next(self._target_cycle))
            self.data.update(next_target=self.data.next_feature.random())
        else:
            self.data.update(next_target=self.data.current_minimap.random_point())
            self.data.update(
                next_feature=self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                )
            )

    def _rotation(self) -> partial:
        if self._prev_pos != self.data.current_minimap_position:
            self.data.update("last_position_change")

        actions = get_to_target(
            self.data.current_minimap_position,
            self.data.next_target,
            self.data.current_minimap,
        )
        if actions:
            self._deadlock_counter = 0
            first_action = actions[0]
            res = self._create_partial(first_action)

            if self._lock is None:
                return res

            elif self._lock.acquire(block=False):
                logger.debug(f"Rotation Lock acquired. Sending Next Random Rotation.")
                return res
        elif self._on_central_target:
            self._deadlock_counter = 0
        else:
            self._deadlock_counter += 1
