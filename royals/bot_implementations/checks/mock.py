import multiprocessing.connection
from functools import partial
from typing import Generator
from botting.core import QueueAction
from botting.core.controls import controller

HANDLE = 0x002E05E6


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
