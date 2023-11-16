import asyncio
import logging
import multiprocessing.connection

from functools import partial
from typing import TYPE_CHECKING

from .action import QueueAction
from royals.game_model import GameData

if TYPE_CHECKING:
    from .bot_monitor import BotMonitor

logger = logging.getLogger(__name__)


class Bot:
    """
    The Bot class is the main entry point for the botting framework.
    It is responsible for packaging all actions received from Bot Monitors (child processes) into a shared queue.
    It is also responsible for creating and cancelling tasks in the shared queue.
    Each Bot instance furthers has a listening loop that listens for actions from the Bot Monitor, which they then put
    into the shared queue (across all Bots).
    """

    shared_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    blocker: asyncio.Event = asyncio.Event()
    logging_queue: multiprocessing.Queue
    all_bots: list["Bot"] = []

    def __init__(
        self, handle: int, ign: str, game_data: GameData, monitor: type["BotMonitor"]
    ) -> None:
        self.handle = handle
        self.ign = ign
        self.game_data = game_data
        self.monitor = monitor

        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.rotation_lock = multiprocessing.Lock()  # Used to manage when map rotation can be enqueued
        self.action_lock = asyncio.Lock()  # Used to manage multiple tasks being enqueued at the same time for a single bot
        self.update_bot_list(self)

        self.monitoring_process: multiprocessing.Process | None = None
        self.main_task: asyncio.Task | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        for bot in Bot.all_bots:
            bot.main_task = asyncio.create_task(
                bot.action_listener(cls.shared_queue), name=repr(bot)
            )
            logger.info(f"Created task {bot.main_task.get_name()}.")

        while True:
            await cls.blocker.wait()  # Blocks all Bots until a task clears the blocker. Used for Stopping/Pausing all bots through user-request from discord.
            queue_item = await cls.shared_queue.get()
            if queue_item is None:
                break

            new_task = cls.create_task(queue_item)
            logger.debug(f"Created task {new_task.get_name()}.")

            if len(asyncio.all_tasks()) > 15:
                logger.warning(
                    f"Number of tasks in the event loop is {len(asyncio.all_tasks())}."
                )

    @classmethod
    def create_task(cls, queue_item: QueueAction) -> asyncio.Task:
        """
        Wrapper around asyncio.create_task which also handles task priority and cancellations.
        It defines how QueueAction objects are converted into asyncio.Task objects and interact with each other.

        Explanations: Tasks are created from QueueAction objects. They also contain a reference
        to the QueueAction object that created them. This is done so that when a task is cancelled,
        the QueueAction object can be re-queued into the shared queue.
        :param queue_item: The QueueAction object to be converted into a task and run asynchronously.
        :return: None
        """
        new_task = asyncio.create_task(queue_item.action(), name=queue_item.identifier)
        new_task.is_in_queue = True

        # Ensures the queue is cleared after the task is done. Callback executes even when task is cancelled.
        new_task.add_done_callback(lambda _: cls.shared_queue.task_done())

        # Add the original QueueAction into the task for re-queuing purposes.
        new_task.action = queue_item.action
        new_task.priority = queue_item.priority
        new_task.is_cancellable = queue_item.is_cancellable

        # Add any other callbacks specified by the QueueAction
        for callback in queue_item.callbacks:
            new_task.add_done_callback(callback)

        # Keep track of when the task was originally created.
        new_task.creation_time = asyncio.get_running_loop().time()

        # Cancel all tasks with lower priority, provided they are cancellable.
        for task in asyncio.all_tasks():
            if getattr(task, "is_in_queue", False):
                if (
                    getattr(task, "priority") > queue_item.priority
                    and getattr(task, "is_cancellable")
                    and not task.done()
                ):
                    logger.debug(
                        f"{queue_item.identifier} has priority over task {task.get_name()}. Cancelling task {task.get_name()}."
                    )
                    task.cancel()

        return new_task

    @classmethod
    def cancel_all(cls):
        cls.shared_queue.put_nowait(None)

    @classmethod
    def update_logging_queue(cls, logging_queue: multiprocessing.Queue) -> None:
        """Updates the logging queue for all bots."""
        cls.logging_queue = logging_queue

    @classmethod
    def update_bot_list(cls, bot: "Bot") -> None:
        """Inserts newly created bot into the bot list."""
        cls.all_bots.append(bot)

    def set_monitoring_process(self) -> None:
        assert (
            self.logging_queue is not None
        ), "Logging queue must be set before setting monitoring process."
        self.monitoring_process = multiprocessing.Process(
            target=self.monitor.start_monitoring,
            name=f"{self} Monitoring",
            args=(self, Bot.logging_queue),
        )

    def _rotation_callback(self, fut):
        """Callback to use on map rotation actions if they need to acquire lock before executing."""
        self.rotation_lock.release()
        logger.debug(f"Rotation Lock released on {self} through callback")

    def _send_update_signal(self, signal: tuple[str], fut):
        """
        Callback to use on map rotation actions if they need to update game data.
        Sends a signal back to the Child process to appropriately update Game Data. This way, CPU-intensive resources
        are not consumed within the main process.
        """
        self.bot_side.send(signal)

    def _wrap_action(self, action: callable) -> callable:
        """
        Wrapper around actions to ensure they are not interfering with each other.
        :param action: The action to be executed asynchronously.
        :return: None
        """
        async def _wrapper():
            await self.action_lock.acquire()
            try:
                logger.debug(f"Action Lock acquired for {self} for {action}")
                await action()
            finally:
                self.action_lock.release()
                logger.debug(f"Action Lock released for {self} for {action}")
        return _wrapper

    async def action_listener(self, queue: asyncio.PriorityQueue) -> None:
        """
        Main Process task.
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.bot_side.poll):
                queue_item: QueueAction = self.bot_side.recv()

                if queue_item is None:
                    logger.debug(
                        f"Received None from {self} monitoring process. Exiting."
                    )
                    self.cancel_all()
                    break

                if queue_item.release_rotation_lock:
                    queue_item.callbacks.append(self._rotation_callback)

                if queue_item.update_game_data is not None:
                    queue_item.callbacks.append(
                        partial(self._send_update_signal, queue_item.update_game_data)
                    )

                # Wrap the action to ensure it is not interfering with other actions from the same bot.
                queue_item.action = self._wrap_action(queue_item.action)

                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
