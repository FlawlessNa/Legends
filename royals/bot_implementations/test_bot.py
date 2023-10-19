import multiprocessing.connection
from functools import partial
from typing import Generator

from royals.core import Bot, QueueAction

HANDLE = 0x001A05F2


def mock_check(pipe: multiprocessing.connection.Connection) -> Generator:
    from royals.core import Controller
    import time

    last_potion = 0
    while True:
        if time.time() - last_potion > 30:
            last_potion = time.time()
            pipe.send(
                QueueAction(
                    priority=0,
                    identifier="mock_check",
                    action=partial(
                        Controller().press, HANDLE, "shift_right", silenced=True
                    ),
                )
            )
            yield


def mock_rotation(pipe: multiprocessing.connection.Connection) -> Generator:
    from royals.core import Controller
    import time

    while True:
        pipe.send(
            QueueAction(
                priority=1,
                identifier="mock_rotation_right",
                action=partial(Controller().move, HANDLE, "right", 5, jump=True),
            )
        )
        time.sleep(10)
        yield
        pipe.send(
            QueueAction(
                priority=1,
                identifier="mock_rotation_left",
                action=partial(Controller().move, HANDLE, "left", 5, jump=True),
            )
        )
        time.sleep(10)
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
