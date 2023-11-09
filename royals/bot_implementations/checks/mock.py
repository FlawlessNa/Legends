import multiprocessing.connection
from functools import partial
from typing import Generator
from royals.core import controller, QueueAction

HANDLE = 0x00620DFE


async def _test_check(key):
    await controller.press(HANDLE, key, silenced=True)


def mock_check(pipe: multiprocessing.connection.Connection) -> Generator:
    import time

    last_potion = 0
    while True:
        if time.time() - last_potion > 10:
            last_potion = time.time()
            pipe.send(
                QueueAction(
                    priority=0,
                    identifier="mock_check",
                    action=partial(_test_check, "insert"),
                ),
            )
        yield