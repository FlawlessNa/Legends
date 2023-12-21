import logging
import math
import multiprocessing as mp

from functools import partial
from typing import Generator

from botting import PARENT_LOG
from botting.core import QueueAction, failsafe_generator
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.actions import random_jump

logger = logging.getLogger(PARENT_LOG + "." + __name__)


async def _rotation_failsafe_response():
    pass


@QueueAction.action_generator(release_lock_on_callback=True, cancellable=True)
@failsafe_generator(max_tries=5, sleep_time=0.5, response=random_jump)
def random_rotation(data: RoyalsData, rotation_lock: mp.Lock = None) -> Generator:
    while True:
        target_pos = data.current_minimap.random_point()
        current_pos = data.current_minimap_position

        while math.dist(current_pos, target_pos) > 2:
            res = None
            data.update("current_minimap_position")
            current_pos = data.current_minimap_position
            actions = get_to_target(current_pos, target_pos, data.current_minimap)
            if actions and not data.currently_attacking:
                first_action = actions[0]
                args = (
                    data.handle,
                    data.ign,
                    first_action.keywords.get("direction", data.current_direction),
                )
                kwargs = first_action.keywords
                kwargs.pop("direction", None)

                if rotation_lock is None:
                    res = partial(first_action.func, *args, **kwargs)

                elif rotation_lock.acquire(block=False):
                    logger.debug(
                        f"Rotation Lock acquired. Sending Next Random Rotation."
                    )
                    res = partial(first_action.func, *args, **kwargs)
            else:
                res = False
                walkable = data.current_minimap.grid.node(*current_pos).walkable
                logger.warning(
                    f"No path to target. Current {current_pos}, Walkable {walkable}"
                )
            yield res
