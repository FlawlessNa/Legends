import itertools
import logging
import math
import multiprocessing as mp
import random
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction
from botting.models_abstractions import Skill
from .base_rotation import Rotation
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.actions import random_jump

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class SmartRotation(Rotation):
    def __init__(
        self,
        data: RoyalsData,
        lock: mp.Lock,
        teleport: Skill = None,
        time_limit: float = 15,
    ) -> None:
        super().__init__(data, lock, teleport)
        self.time_limit = time_limit
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)

        self._next_feature = None  # Used for rotation
        self._next_target = None  # Used for rotation
        self._next_feature_covered = None  # Used for rotation

        self._on_central_target = False  # Impacts rotation behavior
        self._cancellable = True  # Impacts rotation behavior

    def __call__(self):
        if len(self.data.current_minimap.feature_cycle) > 0:
            self._next_feature = random.choice(self.data.current_minimap.feature_cycle)
            self._next_target = self._next_feature.random()
            for _ in range(
                self.data.current_minimap.feature_cycle.index(self._next_feature)
            ):
                next(self._target_cycle)
        else:
            self._next_target = self.data.current_minimap.random_point()
            self._next_feature = self.data.current_minimap.get_feature_containing(
                self._next_target
            )

        self._next_feature_covered = []
        self._last_pos_change = time.perf_counter()
        return iter(self)

    def __next__(self) -> QueueAction | None:
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
                is_cancellable=self._cancellable,
                release_lock_on_callback=True,
            )

    def _set_next_target(self) -> None:
        dist = 5 if self._on_central_target else 2
        if (
            math.dist(self.data.current_minimap_position, self._next_target) > dist
            or self.data.current_minimap_feature != self._next_feature
        ):
            self._on_central_target = False

        elif len(self._next_feature_covered) == 0:
            # We have reached the target position. At this point, cover the platform.
            self._next_target = random.choice(
                [self._next_feature.left_edge, self._next_feature.right_edge]
            )
            self._next_feature_covered.append(self._next_target)

        elif len(self._next_feature_covered) == 1:
            self._next_target = (
                self._next_feature.left_edge
                if self._next_target == self._next_feature.right_edge
                else self._next_feature.right_edge
            )
            self._next_feature_covered.append(self._next_target)

        elif len(self._next_feature_covered) == 2:
            # At this point, we have covered the platform. Now, gravitate towards the center of the feature.
            self._next_target = (
                self._next_feature.central_node
                if self._next_feature.central_node is not None
                else (
                    int(self._next_feature.center[0]),
                    int(self._next_feature.center[1]),
                )
            )
            self._next_feature_covered.append(self._next_target)
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
                    self._next_feature = next(self._target_cycle)
                    self._next_target = self._next_feature.random()
                else:
                    self._next_target = self.data.current_minimap.random_point()
                    self._next_feature = self.data.current_minimap.get_feature_containing(
                        self._next_target
                    )
                self._next_feature_covered.clear()
                self._cancellable = True

    def _single_iteration(self) -> callable:
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
