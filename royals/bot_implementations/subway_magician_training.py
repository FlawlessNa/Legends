import logging
import multiprocessing.connection
from functools import partial
from typing import Generator

from royals.core import Bot, QueueAction
from royals.core import controller

HANDLE = 0x00620DFE
logger = logging.getLogger(__name__)


class SubwayMagicianTraining(Bot):
    def __init__(self, handle: int, ign: str) -> None:
        super().__init__(handle, ign)

    @staticmethod
    def items_to_monitor(
        child_pipe: multiprocessing.connection.Connection,
    ) -> list[callable]:
        return []

    @staticmethod
    def next_map_rotation(
        child_pipe: multiprocessing.connection.Connection,
    ) -> callable:
        return partial(mock_rotation, child_pipe)
