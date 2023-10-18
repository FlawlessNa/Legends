import asyncio
import logging
import multiprocessing

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

    def __init__(self) -> None:
        pass

    def __enter__(self) -> None:
        for bot in Bot.all_bots:
            bot.start_monitoring()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for bot in Bot.all_bots:
            bot.kill()

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
            bot.task.cancel()


class BotMonitor(ChildProcess):
    pass


class Bot(ABC):
    all_bots: list["Bot"] = []

    def __init__(self, handle, ign):
        self.ign = ign
        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.monitoring_loop: BotMonitor = BotMonitor(self.monitoring_side)
        self.controller = Controller(handle=handle, ign=ign)
        self.task: asyncio.Task | None = None
        self.update_bot_list(self)

    @classmethod
    def update_bot_list(cls, bot: "Bot") -> None:
        cls.all_bots.append(bot)

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
