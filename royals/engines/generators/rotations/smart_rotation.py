import itertools
import logging
import math
import multiprocessing as mp
import random
import time
from functools import partial

from botting import PARENT_LOG

from botting.models_abstractions import Skill
from .base_rotation import Rotation
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
        time_limit: float = 15,
    ) -> None:
        super().__init__(data, lock, training_skill, mob_threshold, teleport)
        self.time_limit = time_limit
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)

        self._next_feature_covered = []  # Used for rotation

        self._on_central_target = False  # Impacts rotation behavior
        self._cancellable = True  # Impacts rotation behavior

        if len(self.data.current_minimap.feature_cycle) > 0:
            self.data.update(
                next_feature=random.choice(self.data.current_minimap.feature_cycle)
            )
            self.data.update(next_target=self.data.next_feature.random())
            for _ in range(
                self.data.current_minimap.feature_cycle.index(self.data.next_feature)
            ):
                next(self._target_cycle)
        else:
            self.data.update(next_target=self.data.current_minimap.random_point())
            self.data.update(
                next_feature=self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                )
            )

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
        dist = 5 if self._on_central_target else 2
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target) > dist
            or self.data.current_minimap_feature != self.data.next_feature
        ):
            self._on_central_target = False

        elif len(self._next_feature_covered) == 0:
            # We have reached the target position. At this point, cover the platform.
            self.data.update(
                next_target=random.choice(
                    [
                        self.data.next_feature.left_edge,
                        self.data.next_feature.right_edge,
                    ]
                )
            )
            self._next_feature_covered.append(self.data.next_target)

        elif len(self._next_feature_covered) == 1:
            self.data.update(
                next_target=(
                    self.data.next_feature.left_edge
                    if self.data.next_target[0] >= self.data.next_feature.center[0]
                    else self.data.next_feature.right_edge
                )
            )
            self._next_feature_covered.append(self.data.next_target)

        elif len(self._next_feature_covered) == 2:
            # At this point, we have covered the platform. Now, gravitate towards the center of the feature.
            self.data.update(
                next_target=(
                    self.data.next_feature.central_node
                    if self.data.next_feature.central_node is not None
                    else (
                        int(self.data.next_feature.center[0]),
                        int(self.data.next_feature.center[1]),
                    )
                )
            )
            self._next_feature_covered.append(self.data.next_target)
            self._cancellable = False
            self._center_targeted_at = time.perf_counter()

        else:
            self._on_central_target = True
            # Once the center of the feature is targeted, stay there for X seconds before rotating.
            if (
                time.perf_counter() - self.data.last_mob_detection > 2
                or time.perf_counter() - self._center_targeted_at > self.time_limit
            ):
                if len(self.data.current_minimap.feature_cycle) > 0:
                    self.data.update(next_feature=next(self._target_cycle))
                    self.data.update(next_target=self.data.next_feature.random())
                else:
                    self.data.update(
                        next_target=self.data.current_minimap.random_point()
                    )
                    self.data.update(
                        next_feature=self.data.current_minimap.get_feature_containing(
                            self.data.next_target
                        )
                    )
                self._next_feature_covered.clear()
                self._cancellable = True

    def _rotation(self) -> partial:
        res = None

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
