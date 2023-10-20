import asyncio
import logging
import multiprocessing.connection
import time

from abc import ABC, abstractmethod

from royals.utilities import ChildProcess

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
                target=self.start_monitoring,
                name=f"{bot} Monitoring",
                # args=(
                #     bot.monitoring_side,
                #     self.logging_queue,
                #     repr(bot),
                #     bot.items_to_monitor,
                #     bot.next_map_rotation,
                # ),
                args=(bot, self.logging_queue),
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

            if queue_item.callback is not None:
                new_task.add_done_callback(queue_item.callback)

            logger.debug(f"Created task {new_task}.")

            if len(asyncio.all_tasks()) > 15:
                logger.warning(
                    f"Number of tasks in the event loop is {len(asyncio.all_tasks())}."
                )

    @staticmethod
    def start_monitoring(
        bot: "Bot",
        log_queue: multiprocessing.Queue,
        # pipe_end: multiprocessing.connection.Connection,
        # log_queue: multiprocessing.Queue,
        # source: str,
        # items_to_monitor: list[Generator],
        # next_map_rotation: Generator,
    ):
        ChildProcess.set_log_queue(log_queue)
        monitor = BotMonitor(bot)
        monitor.start()

    @classmethod
    def cancel_all(cls):
        cls.shared_queue.put_nowait(None)


class BotMonitor(ChildProcess):
    def __init__(
        self,
        bot: "Bot"
        # pipe_end: multiprocessing.connection.Connection,
        # source: str,
        # monitor: list[callable],
        # next_map_rotation: callable,
        # rotation_lock: multiprocessing.Lock
    ) -> None:
        super().__init__(bot.monitoring_side)
        self.source = repr(bot)
        self.monitoring_generators = bot.items_to_monitor
        self.map_rotation_generator = bot.next_map_rotation
        self.rotation_lock = bot.rotation_lock

    def start(self) -> None:
        """
        There are two types of generators that are monitored:
        1. Generators that are used to monitor the game state (potions, pet food, inventories, chat feed, proper map, etc).
        2. Generators that are used to determine the next map rotation.
        On every iteration, all generators from 1. are checked once.
        Then, the map rotation generator is checked whenever the bot is ready to perform an action related to map rotation.
        :return: None
        """
        try:
            generators = [
                gen() for gen in self.monitoring_generators(self.pipe_end)
            ]  # Instantiate all generators
            map_rotation = self.map_rotation_generator(self.pipe_end)()

            while True:
                # If main process sends None, it means we are exiting.
                if self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        break

                before = time.time()
                for check in generators:
                    next(check)
                # logger.debug(
                #     f"Time taken to execute all checks for {repr(self.source)}: {time.time() - before}"
                # )

                if self.rotation_lock.acquire(block=False):
                    logger.debug(f"Acquired lock for {self.source} map rotation. Calling next rotation")
                    next(map_rotation)

        except Exception as e:
            raise

        finally:
            if not self.pipe_end.closed:
                self.pipe_end.send(None)
                self.pipe_end.close()

from functools import partial
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
                    queue_item.callback = partial(self._rotation_callback, lock=self.rotation_lock, source=repr(self))
                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
