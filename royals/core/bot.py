import asyncio
import logging
import multiprocessing.connection

from abc import ABC, abstractmethod

from .controls import Controller
from ..utilities import ChildProcess

logger = logging.getLogger(__name__)


class BotLauncher:
    """
    Launcher class for all Bots.
    A single, shared asynchronous queue (class attribute) is used to schedule all Bots. This ensures that no two Bots are running in parallel, which would be suspicious.
    Instead of true parallelism, this fully leverages cooperative multitasking.
    Additionally, it defines synchronization primitives that can be used by all bots as well.
    """

    shared_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    blocker: asyncio.Event = asyncio.Event()

    def __init__(self, logging_queue: multiprocessing.Queue) -> None:
        self.logging_queue = logging_queue

    def __enter__(self) -> None:
        for bot in Bot.all_bots:
            bot.monitoring_process = multiprocessing.Process(
                target=bot.start_monitoring,
                name=f"{bot} Monitoring",
                args=(bot.monitoring_side, self.logging_queue, repr(bot)),
            )
            bot.monitoring_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for bot in Bot.all_bots:
            bot.bot_side.send(None)
            bot.bot_side.close()
            logger.debug(f"Sent stop signal to {bot} monitoring process")
            bot.monitoring_process.join()
            logger.debug(f"Joined {bot} monitoring process")

            logger.debug(f"Stopping {bot} main task")
            bot.main_task.cancel()

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        for bot in Bot.all_bots:
            bot.main_task = asyncio.create_task(
                bot.action_listener(cls.shared_queue), name=repr(bot)
            )
            logger.info(f"Created task {bot.main_task}.")

        while True:
            await cls.blocker.wait()  # Blocks all Bots until a task clears the blocker. Used for Stopping/Pausing all bots through user-request from discord.
            queue_item = await cls.shared_queue.get()
            if queue_item is None:
                break

            # Adds the task into the main event loop
            new_task = asyncio.create_task(
                queue_item.action(), name=queue_item.identifier
            )

            # Ensures the queue is cleared after the task is done. Callback executes even when task is cancelled.
            new_task.add_done_callback(lambda _: cls.shared_queue.task_done())

            logger.debug(f"Created task {new_task}.")

            if len(asyncio.all_tasks()) > 15:
                logger.warning(
                    f"Number of tasks in the event loop is {len(asyncio.all_tasks())}."
                )

    @classmethod
    def cancel_all(cls):
        cls.shared_queue.put_nowait(None)


async def func():
    await asyncio.sleep(3)
    print("test")


class BotMonitor(ChildProcess):
    def __init__(
        self, pipe_end: multiprocessing.connection.Connection, source: str
    ) -> None:
        super().__init__(pipe_end)
        self.source = source

    def start(self) -> None:
        try:
            from .action import QueueAction
            import time

            # TODO - Implement multiprocessing.Lock on the monitoring to only send items through queue when the bot is ready - meaning it has finished executing the previous action. Use add_done_callback to set the Lock.
            while True:
                if self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        break

                queue_item1 = QueueAction.from_tuple((0, self.source, func))
                logger.debug(f"Sending {queue_item1} to main process.")
                self.pipe_end.send(queue_item1)
                time.sleep(1)
        finally:
            if not self.pipe_end.closed:
                self.pipe_end.close()


class Bot(ABC):
    all_bots: list["Bot"] = []

    def __init__(self, handle, ign):
        self.ign = ign
        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.controller = Controller(handle=handle, ign=ign)
        self.update_bot_list(self)
        self.main_task: asyncio.Task | None = None
        self.monitoring_process: multiprocessing.Process | None = None

    @classmethod
    def update_bot_list(cls, bot: "Bot") -> None:
        cls.all_bots.append(bot)

    @staticmethod
    def start_monitoring(
        pipe_end: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
        source: str,
    ):
        ChildProcess.set_log_queue(log_queue)
        monitor = BotMonitor(pipe_end, source)
        monitor.start()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    async def action_listener(self, queue: asyncio.PriorityQueue) -> None:
        """
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.bot_side.poll):
                queue_item = self.bot_side.recv()
                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
