import itertools
import logging
import multiprocessing.connection
from functools import partial
from typing import Generator

from royals.core import Bot, QueueAction
from .actions.mock import _test_action
from .checks.mock import mock_check

logger = logging.getLogger(__name__)


class TestBot(Bot):
    def __init__(self, handle: int, ign: str) -> None:
        super().__init__(handle, ign)

    @staticmethod
    def items_to_monitor(
        child_pipe: multiprocessing.connection.Connection,
    ) -> list[callable]:
        return [partial(mock_check, child_pipe)]

    @staticmethod
    def next_map_rotation(
        child_pipe: multiprocessing.connection.Connection,
    ) -> Generator:

        direction = itertools.cycle(["left", "right"])
        while True:
            child_pipe.send(
                QueueAction(
                    priority=1,
                    identifier="mock_rotation",
                    action=partial(_test_action, next(direction)),
                )
            )
            yield
