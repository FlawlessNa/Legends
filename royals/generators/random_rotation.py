import logging
import math
import multiprocessing as mp

from functools import partial
from typing import Generator

from botting import PARENT_LOG
from botting.core import QueueAction
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.actions import random_jump

logger = logging.getLogger(PARENT_LOG + "." + __name__)


@QueueAction.action_generator(release_lock_on_callback=True, cancellable=True)
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
            yield res
