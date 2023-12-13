import itertools
import logging
import multiprocessing

from functools import partial

import botting
from botting.core import QueueAction, DecisionEngine, Executor
from .actions.mock import _test_action
from .checks.mock import mock_check

logger = logging.getLogger(f'{botting.PARENT_LOG}.{__name__}')


class TestBot(DecisionEngine):
    def __init__(self, log_queue: multiprocessing.Queue, bot: Executor) -> None:
        super().__init__(log_queue, bot)

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> list[callable]:
        return [self.mock_rotation]

    def mock_rotation(self) -> None:
        direction = itertools.cycle(["left", "right"])

        while True:
            if self.watched_bot.rotation_lock.acquire(block=False):
                logger.debug(
                    "Rotation Lock acquired. Next action is being sent to main queue."
                )
                self.pipe_end.send(
                    QueueAction(
                        priority=1,
                        identifier="mock_rotation",
                        action=partial(_test_action, next(direction)),
                        release_rotation_lock=True,
                        is_cancellable=True,
                        update_game_data=("test_mock",),
                    )
                )
            yield
