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
                name=repr(bot),
                args=(bot.monitoring_side, self.logging_queue)
            )
            bot.monitoring_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for bot in Bot.all_bots:
            bot.bot_side.send(None)
            bot.bot_side.close()
            logger.debug(f"Sent stop signal to {bot} process")

            logger.debug(f"Stopping the {bot} main task")
            bot.main_task.cancel()
            bot.monitoring_process.join()

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        for bot in Bot.all_bots:
            bot.task = asyncio.create_task(bot.enqueue_next_actions(cls.shared_queue), name=repr(bot))

        while True:
            await cls.blocker.wait()  # Blocks all Bots until a task clears the blocker. Used for Stopping/Pausing all bots through user-request from discord.
            queue_item = await cls.shared_queue.get()

            new_task = asyncio.create_task(
                queue_item.action(), name=queue_item.name
            )  # Adds the task into the main event loop

            # TODO - remove test callback and uncomment the lambda if it works
            # new_task.add_done_callback(
            #     lambda _: cls.shared_queue.task_done()
            # )  # Ensures the queue is cleared after the task is done.

            def _test_callback(fut):
                print(
                    f"callback has been called on future {fut} to clear the queue. Prior size: {cls.shared_queue.qsize()}"
                )
                cls.shared_queue.task_done()
                print(
                    f"callback has been called on future {fut} to clear the queue. After size: {cls.shared_queue.qsize()}"
                )
            new_task.add_done_callback(_test_callback)

    @staticmethod
    def cancel_all_bots():
        for bot in Bot.all_bots:
            bot.main_task.cancel()


class BotMonitor(ChildProcess):
    def __init__(self, pipe_end: multiprocessing.connection.Connection) -> None:
        super().__init__(pipe_end)

    def start(self) -> None:
        while True:
            try:
                pass
            finally:
                if not self.pipe_end.closed:
                    self.pipe_end.send(None)
                    self.pipe_end.close()
                    break


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
    ):
        ChildProcess.set_log_queue(log_queue)
        monitor = BotMonitor(pipe_end)
        monitor.start()

    def __repr__(self) -> str:
        return f"Bot({self.__class__.__name__})--({self.ign})"

    async def enqueue_next_actions(self, queue: asyncio.PriorityQueue) -> None:
        """
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.bot_side.poll):
                queue_item = self.bot_side.recv()
                await queue.put(queue_item)
