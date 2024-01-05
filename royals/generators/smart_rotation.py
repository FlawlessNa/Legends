import itertools
import logging
import math
import multiprocessing as mp
import random
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction
from botting.models_abstractions import Skill
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.actions import random_jump

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class SmartRotation(DecisionGenerator):
    def __init__(self, data: RoyalsData, lock: mp.Lock, teleport: Skill = None, time_limit: float = 15) -> None:
        self.data = data
        self.time_limit = time_limit
        self._lock = lock
        self._teleport = teleport
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)

        self._next_feature = None  # Used for rotation
        self._next_target = None  # Used for rotation
        self._next_feature_covered = None  # Used for rotation

        self._last_pos_change = None  # Used for failsafe
        self._deadlock_counter = 0  # Used for failsafe

        self._on_central_target = False  # Impacts rotation behavior
        self._cancellable = True  # Impacts rotation behavior

    def __call__(self):
        self._next_feature = random.choice(self.data.current_minimap.feature_cycle)
        self._next_target = self._next_feature.random()
        self._next_feature_covered = []

        for _ in range(
            self.data.current_minimap.feature_cycle.index(self._next_feature)
        ):
            next(self._target_cycle)

        self._last_pos_change = time.perf_counter()
        self.data.current_minimap.set_teleport_allowed(True if self._teleport is not None else False)

        return iter(self)

    def __next__(self) -> QueueAction | None:
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
            if time.perf_counter() - self.data.last_mob_detection > 2:
                self._next_feature = next(self._target_cycle)
                self._next_target = self._next_feature.random()
                self._next_feature_covered.clear()
                self._cancellable = True

            elif time.perf_counter() - self._center_targeted_at > self.time_limit:
                self._next_feature = next(self._target_cycle)
                self._next_target = self._next_feature.random()
                self._next_feature_covered.clear()
                self._cancellable = True

    def _single_iteration(self) -> callable:
        res = None
        prev_pos = self.data.current_minimap_position
        self.data.update("current_minimap_position")

        if prev_pos != self.data.current_minimap_position:
            self._last_pos_change = time.perf_counter()

        actions = get_to_target(
            self.data.current_minimap_position,
            self._next_target,
            self.data.current_minimap,
            True if self._teleport is not None else False,
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
        elif self._on_central_target:
            self._deadlock_counter = 0
        else:
            self._deadlock_counter += 1

        return res

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
