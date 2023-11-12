import asyncio
import logging
import multiprocessing.connection

from typing import TYPE_CHECKING

from .action import QueueAction
from royals.game_model import GameData

if TYPE_CHECKING:
    from .bot_monitor import BotMonitor

logger = logging.getLogger(__name__)


class Bot:
    shared_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    blocker: asyncio.Event = asyncio.Event()
    logging_queue: multiprocessing.Queue
    all_bots: list["Bot"] = []

    def __init__(
        self, handle: int, ign: str, game_data: GameData, monitor: type["BotMonitor"]
    ) -> None:
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

            # for task in asyncio.all_tasks():
            #     if getattr(task, "priority", 0) > queue_item.priority:
            #         logger.debug(
            #             f"{queue_item.identifier} has priority over task {task.get_name()}. Cancelling task."
            #         )
            #         task.cancel()

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
        if queue_item.callback is not None:
            new_task.add_done_callback(queue_item.callback)

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
                queue_item: QueueAction = self.bot_side.recv()

                if queue_item is None:
                    logger.debug(
                        f"Received None from {self} monitoring process. Exiting."
                    )
                    self.cancel_all()
                    break

                if queue_item.release_rotation_lock:
                    queue_item.callback = self._rotation_callback

                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                await queue.put(queue_item)
