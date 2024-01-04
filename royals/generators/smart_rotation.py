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
    def __init__(self,
                 data: RoyalsData,
                 lock: mp.Lock,
                 teleport: Skill = None) -> None:
        self.data = data
        self._lock = lock
        self._teleport = teleport
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)
        self._next_feature = self._next_target = self._next_feature_covered = self._last_failsafe_called_at = self._last_pos = None
        self._failsafe_counter = 0

    def __call__(self):
        self._next_feature = random.choice(self.data.current_minimap.feature_cycle)
        self._next_target = self._next_feature.random()
        self._next_feature_covered = []
        self._last_failsafe_called_at = time.perf_counter()
        for _ in range(self.data.current_minimap.feature_cycle.index(self._next_feature)):
            next(self._target_cycle)

        return iter(self)

    def __next__(self) -> QueueAction | None:
        self._set_next_target()
        res = self._single_iteration()
        if res is False:
            res = self._failsafe()
        return res

    def _set_next_target(self) -> None:
        if (
            math.dist(self.data.current_minimap_position, self._next_target) > 2
            or self.data.current_minimap_feature != self._next_feature
        ):
            pass

        elif len(self._next_feature_covered) == 0:
            # We have reached the target position. At this point, cover the platform.
            self._next_target = random.choice([self._next_feature.left_edge, self._next_feature.right_edge])
            self._next_feature_covered.append(self._next_target)

        elif len(self._next_feature_covered) == 1:
            self._next_target = self._next_feature.left_edge if self._next_target == self._next_feature.right_edge else self._next_feature.right_edge
            self._next_feature_covered.append(self._next_target)

        elif len(self._next_feature_covered) == 2:
            # At this point, we have covered the platform. Now, gravitate towards the center of the feature.
            self._next_target = self._next_feature.central_node if self._next_feature.central_node is not None else (int(self._next_feature.center[0]), int(self._next_feature.center[1]))
            self._next_feature_covered.append(self._next_target)

        else:
            # Once the center of the feature is targeted, stay there for X seconds before rotating.
            if time.perf_counter() - self.data.last_mob_detection > 5:
                self._next_feature = next(self._target_cycle)
                self._next_target = self._next_feature.random()
                self._next_feature_covered.clear()
            print(f'time since last detection = {time.perf_counter() - self.data.last_mob_detection}')

    def _single_iteration(self) -> callable | None:
        res = None
        self.data.update("current_minimap_position")
        self._last_pos = self.data.current_minimap_position
        actions = get_to_target(
            self.data.current_minimap_position,
            self._next_target,
            self.data.current_minimap,
            True if self._teleport is not None else False,
        )
        if actions and not self.data.currently_attacking:
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
        elif self.data.currently_attacking:
            pass
        else:
            res = False
        return res

    def _failsafe(self) -> callable | None:
        if time.perf_counter() - self._last_failsafe_called_at > 5:
            # Reset failsafe counters if it hasn't been called for a while and perform checks
            self._last_failsafe_called_at = time.perf_counter()
            self._failsafe_counter = 1
        else:
            self._failsafe_counter += 1

        if self._failsafe_counter > 5:
            breakpoint()


#
# @QueueAction.action_generator(release_lock_on_callback=True, cancellable=True)
# @failsafe_generator(max_tries=5, sleep_time=0.5, response=random_jump)
# def smart_rotation(
#     data: RoyalsData,
#     rotation_lock: mp.Lock = None,
#     teleport: Skill = None,
# ) -> Generator:
#     """
#     Generator for smart rotation.
#     Cycle through the features of the current minimap that are to be cycled through.
#     Every time a new feature is selected, get to that feature. Then, stay in that feature
#     for desired amount of time. Once the time is up, go to next feature and repeat.
#     :param data:
#     :param rotation_lock:
#     :param teleport:
#     :return:
#     """
#
#     # Start by selecting a random feature for the first destination.
#     target_features = itertools.cycle(data.current_minimap.feature_cycle)
#     next_feature = random.choice(data.current_minimap.feature_cycle)
#     for _ in range(data.current_minimap.feature_cycle.index(next_feature)):
#         next(target_features)
#
#     while True:
#         next_feature = next(target_features)
#         target_pos = next_feature.random()
#
#         while (
#             math.dist(data.current_minimap_position, target_pos) > 2
#             or data.current_minimap_feature != next_feature
#         ):
#             yield _single_iteration(data, target_pos, rotation_lock, teleport)
#
#         # Once the inner loop is done, it means we are at the target feature.
#         # Start by covering the features coverage_area while blindly attacking.
#         # Then, gravitate towards the central_point of the feature until no more mobs are detected for X seconds.
#         # TODO - Figure out systematic way to continuously attack mobs
#         assert (
#             next_feature.is_platform
#         ), f"Feature {next_feature.name} is not a platform."
#         left_edge = next_feature.left_edge
#         right_edge = next_feature.right_edge
#         target_pos = (
#             left_edge
#             if data.current_minimap_position[0] <= next_feature.center[0]
#             else right_edge
#         )
#
#         while math.dist(data.current_minimap_position, target_pos) > 2:
#             yield _single_iteration(data, target_pos, rotation_lock, teleport)
#         target_pos = left_edge if target_pos == right_edge else right_edge
#         while math.dist(data.current_minimap_position, target_pos) > 2:
#             yield _single_iteration(data, target_pos, rotation_lock, teleport)
#
#         # At this point the coverage area is covered. Now, gravitate towards the center of the feature.
#         target_pos = (
#             next_feature.central_node
#             if next_feature.central_node is not None
#             else (int(next_feature.center[0]), int(next_feature.center[1]))
#         )
#         while (
#             math.dist(data.current_minimap_position, target_pos) > 2
#             and time.perf_counter() - data.last_mob_detection > 4
#         ):
#             yield _single_iteration(data, target_pos, rotation_lock, teleport)
#
#
# def _single_iteration(
#     data: RoyalsData,
#     target_pos: tuple[int, int],
#     rotation_lock: mp.Lock = None,
#     teleport: Skill = None,
# ):
#     """
#     Single iteration of smart rotation.
#     :param data:
#     :param rotation_lock:
#     :return:
#     """
#     res = None
#     data.update("current_minimap_position")
#     current_pos = data.current_minimap_position
#     actions = get_to_target(
#         current_pos,
#         target_pos,
#         data.current_minimap,
#         True if teleport is not None else False,
#     )
#     if actions and not data.currently_attacking:
#         first_action = actions[0]
#         args = (
#             data.handle,
#             data.ign,
#             first_action.keywords.get("direction", data.current_direction),
#         )
#         kwargs = first_action.keywords
#         kwargs.pop("direction", None)
#         if first_action.func.__name__ == "teleport":
#             kwargs.update(teleport_skill=teleport)
#
#         if rotation_lock is None:
#             res = partial(first_action.func, *args, **kwargs)
#
#         elif rotation_lock.acquire(block=False):
#             logger.debug(f"Rotation Lock acquired. Sending Next Random Rotation.")
#             res = partial(first_action.func, *args, **kwargs)
#     elif data.currently_attacking:
#         pass
#     else:
#         res = False
#     return res
