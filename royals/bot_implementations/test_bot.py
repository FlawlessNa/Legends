import logging
import multiprocessing.connection
from functools import partial
from typing import Generator

from royals.core import Bot, QueueAction
from royals.core import Controller

HANDLE = 0x011205E2
logger = logging.getLogger(__name__)


async def _test(direction):
    await Controller().move(HANDLE, "FarmFest1", direction, 5)


async def _test_check(key):
    await Controller().press(HANDLE, key, silenced=True)


def mock_check(pipe: multiprocessing.connection.Connection) -> Generator:
    import time

    last_potion = 0
    while True:
        if time.time() - last_potion > 30:
            last_potion = time.time()
            pipe.send(
                QueueAction(
                    priority=0,
                    identifier="mock_check",
                    action=partial(_test_check, "insert"),
                ),
            )
        yield


def mock_rotation(pipe: multiprocessing.connection.Connection) -> Generator:
    import itertools

    direction = itertools.cycle(["left", "right"])

    while True:
        pipe.send(
            QueueAction(
                priority=1,
                identifier="mock_rotation",
                action=partial(_test, next(direction)),
            )
        )
        yield


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
    ) -> callable:
        return partial(mock_rotation, child_pipe)
