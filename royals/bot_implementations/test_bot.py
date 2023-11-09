import itertools
import logging
import multiprocessing.connection
from functools import partial
from typing import Generator

from royals.core import QueueAction, BotMonitor, Bot
from .actions.mock import _test_action
from .checks.mock import mock_check

logger = logging.getLogger(__name__)


class TestBot(BotMonitor):
    def __init__(self, bot: "Bot") -> None:
        super().__init__(bot)

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> Generator:

        direction = itertools.cycle(["left", "right"])
        while True:
            self.pipe_end.send(
                QueueAction(
                    priority=1,
                    identifier="mock_rotation",
                    action=partial(_test_action, next(direction)),
                )
            )
            yield
