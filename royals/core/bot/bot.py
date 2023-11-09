import asyncio
import logging
import multiprocessing.connection

from abc import ABC, abstractmethod
from functools import partial

logger = logging.getLogger(__name__)


class Bot(ABC):
    all_bots: list["Bot"] = []

    def __init__(self, handle, ign):
        self.handle = handle
        self.ign = ign
        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.rotation_lock = multiprocessing.Lock()
        self.update_bot_list(self)
        self.main_task: asyncio.Task | None = None
        self.monitoring_process: multiprocessing.Process | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    @classmethod
    def update_bot_list(cls, bot: "Bot") -> None:
        cls.all_bots.append(bot)

    @staticmethod
    @abstractmethod
    def items_to_monitor(child_pipe: multiprocessing.Pipe) -> list[callable]:
        """
        This property is used to define the items that are monitored by the monitoring loop.
        Each item in this list is an iterator.
        At each loop iteration, next() is called on each item in this list, at which point the generator may send an action through the multiprocess pipe.
        :return: List of items to monitor.
        """
        pass

    @staticmethod
    @abstractmethod
    def next_map_rotation(child_pipe: multiprocessing.Pipe) -> callable:
        pass

    @staticmethod
    def _rotation_callback(fut, *, lock: multiprocessing, source: str):
        logger.debug(f"Callback called on {source} to release Rotation Lock")
        lock.release()

    async def action_listener(self, queue: asyncio.PriorityQueue) -> None:
        """
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.bot_side.poll):
                queue_item = self.bot_side.recv()
                if queue_item.identifier == "mock_rotation":
                    queue_item.callback = partial(
                        self._rotation_callback,
                        lock=self.rotation_lock,
                        source=repr(self),
                    )
                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
