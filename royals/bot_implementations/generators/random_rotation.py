import logging
import math
import multiprocessing as mp

from functools import partial
from typing import Generator

from botting import PARENT_LOG
from botting.core import QueueAction
from royals import RoyalsData
from royals.models_implementations.mechanics.path_into_movements import get_to_target

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
            yield res


# def random_rotation(data: RoyalsData) -> Generator:
#     while True:
#         err_count = 0
#         target_pos = data.current_minimap.random_point()
#         current_pos = data.current_minimap_position
#
#         while math.dist(current_pos, target_pos) > 2:
#             data.update("current_minimap_position")
#             current_pos = data.current_minimap_position
#             actions = get_to_target(current_pos, target_pos, data.current_minimap)
#             try:
#                 first_action = actions[0]
#                 assert (
#                     first_action.args == tuple()
#                 )  # Ensures arguments are keywords-only
#                 args = (
#                     data.handle,
#                     data.ign,
#                     first_action.keywords.get("direction", data.current_direction),
#                 )
#                 kwargs = getattr(first_action, "keywords", {})
#                 kwargs.pop("direction", None)
#                 err_count = 0
#                 yield partial(first_action.func, *args, **kwargs)
#             except IndexError:
#                 if err_count > 10:
#                     logger.error("Could not understand where the fk we are")
#                     raise RuntimeError("Unable to understand where the fk we are")
#                 elif err_count > 2:
#                     direction = random.choice(["left", "right"])
#                     yield partial(
#                         controller.move,
#                         data.handle,
#                         data.ign,
#                         direction,
#                         duration=1,
#                         jump=True,
#                     )
#                     time.sleep(1)
#
#                 if not data.current_minimap.grid.node(*current_pos).walkable:
#                     err_count += 1
#                     time.sleep(1)
