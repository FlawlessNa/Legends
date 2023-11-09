import asyncio
import logging
import multiprocessing.connection

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot_monitor import BotMonitor

logger = logging.getLogger(__name__)


class Bot:
    logging_queue: multiprocessing.Queue
    all_bots: list["Bot"] = []

    def __init__(self, handle: int, ign: str, monitor: type["BotMonitor"]) -> None:
        self.handle = handle
        self.ign = ign
        self.monitor = monitor

        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.rotation_lock = multiprocessing.Lock()
        self.update_bot_list(self)

        self.monitoring_process: multiprocessing.Process | None = None
        self.main_task: asyncio.Task | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    @classmethod
    def update_logging_queue(cls, logging_queue: multiprocessing.Queue) -> None:
        """Updates the logging queue for all bots."""
        cls.logging_queue = logging_queue

    @classmethod
    def update_bot_list(cls, bot: "Bot") -> None:
        """Inserts newly created bot into the bot list."""
        cls.all_bots.append(bot)

    def set_monitoring_process(self) -> None:
        assert self.logging_queue is not None, "Logging queue must be set before setting monitoring process."
        self.monitoring_process = multiprocessing.Process(
            target=self.monitor.start_monitoring,
            name=f"{self} Monitoring",
            args=(self, Bot.logging_queue),
        )

    def _rotation_callback(self, fut):
        logger.debug(f"Callback called on {self} to release Rotation Lock")
        self.rotation_lock.release()

    async def action_listener(self, queue: asyncio.PriorityQueue) -> None:
        """
        Main Process task.
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.bot_side.poll):
                queue_item = self.bot_side.recv()
                if queue_item.identifier == "mock_rotation":
                    queue_item.callback = self._rotation_callback
                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
