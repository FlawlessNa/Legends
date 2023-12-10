import logging
import math
import multiprocessing

from functools import partial

import botting
import royals

from botting.core import QueueAction, BotMonitor, Bot
from .actions.pathfinding import _get_path_to_target
from .checks.mock import mock_check

logger = logging.getLogger(f"{botting.PARENT_LOG}.{__name__}")


class LudiFreeMarketRoaming(BotMonitor):
    def __init__(self, log_queue: multiprocessing.Queue, bot: Bot) -> None:
        super().__init__(log_queue, bot)
        self.game_data: royals.RoyalsData = bot.game_data

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> list[callable]:
        return [self.random_rotation]

    def random_rotation(self) -> None:
        while True:
            target = self.game_data.current_minimap.random_point()

            while (
                math.dist(self.game_data.current_minimap_position, target) > 5
            ):  # TODO - Find proper threshold
                self.game_data.update("current_minimap_position")

                if self.watched_bot.rotation_lock.acquire(block=False):
                    logger.debug(
                        "Rotation Lock acquired. Next action is being sent to main queue."
                    )
                    tasks = _get_path_to_target(
                        self.game_data.current_minimap_position,
                        target,
                        self.game_data.handle,
                        self.game_data.current_minimap,
                    )
                    if tasks:
                        print(tasks[0])
                        self.pipe_end.send(
                            QueueAction(
                                priority=10,
                                identifier="Map Rotation",
                                action=tasks[0],
                                is_cancellable=True,
                                is_map_rotation=True,
                                release_rotation_lock=True,
                                update_game_data=("current_minimap_position",),
                            )
                        )
                    else:
                        logger.debug("Rotation Lock released since to task found.")
                        self.watched_bot.rotation_lock.release()
                yield
