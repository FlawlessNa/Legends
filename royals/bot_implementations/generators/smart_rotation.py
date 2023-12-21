import itertools
import logging
import math
import multiprocessing as mp
import random
import time

from functools import partial
from typing import Generator

from botting import PARENT_LOG
from botting.core import QueueAction, failsafe_generator
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.models_implementations.characters.skills import Skill
from royals.actions import random_jump

logger = logging.getLogger(PARENT_LOG + "." + __name__)


@QueueAction.action_generator(release_lock_on_callback=True, cancellable=True)
@failsafe_generator(max_tries=5, sleep_time=0.5, response=random_jump)
def smart_rotation(
        data: RoyalsData,
        rotation_lock: mp.Lock = None,
        time_spent_on_feature: float = 10,
        teleport: Skill = None,
) -> Generator:
    """
    Generator for smart rotation.
    Cycle through the features of the current minimap that are to be cycled through.
    Every time a new feature is selected, get to that feature. Then, stay in that feature
    for desired amount of time. Once the time is up, go to next feature and repeat.
    :param data:
    :param rotation_lock:
    :param time_spent_on_feature:
    :param teleport:
    :return:
    """

    # Start by selecting a random feature for the first destination.
    target_features = itertools.cycle(data.current_minimap.feature_cycle)
    next_feature = random.choice(data.current_minimap.feature_cycle)
    for _ in range(data.current_minimap.feature_cycle.index(next_feature)):
        next(target_features)

    while True:
        next_feature = next(target_features)
        target_pos = next_feature.random()

        while math.dist(data.current_minimap_position, target_pos) > 2 and data.current_minimap_feature != next_feature:
            yield _single_iteration(data, target_pos, rotation_lock, teleport)

        # Once the inner loop is broken, it means we are at the target feature.
        # Stay there for a while.
        time_reached = time.perf_counter()
        while time.perf_counter() - time_reached < time_spent_on_feature:
            target_pos = next_feature.random()
            while math.dist(data.current_minimap_position, target_pos) > 2:
                yield _single_iteration(data, target_pos, rotation_lock, teleport)


def _single_iteration(data: RoyalsData,
                      target_pos: tuple[int, int],
                      rotation_lock: mp.Lock = None,
                      teleport: Skill = None):
    """
    Single iteration of smart rotation.
    :param data:
    :param rotation_lock:
    :return:
    """
    res = None
    data.update("current_minimap_position")
    current_pos = data.current_minimap_position
    actions = get_to_target(current_pos, target_pos, data.current_minimap, teleport)
    if actions and not data.currently_attacking:
        first_action = actions[0]
        args = (
            data.handle,
            data.ign,
            first_action.keywords.get("direction", data.current_direction),
        )
        kwargs = first_action.keywords
        kwargs.pop("direction", None)
        if first_action.func.__name__ == 'teleport':
            kwargs.update(teleport_skill=teleport)

        if rotation_lock is None:
            res = partial(first_action.func, *args, **kwargs)

        elif rotation_lock.acquire(block=False):
            logger.debug(
                f"Rotation Lock acquired. Sending Next Random Rotation."
            )
            res = partial(first_action.func, *args, **kwargs)
    else:
        res = False
    return res
