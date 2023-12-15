import asyncio
import logging
import multiprocessing.connection

from functools import partial
from typing import TYPE_CHECKING

from .action import QueueAction
from botting.utilities import client_handler

if TYPE_CHECKING:
    from .decision_engine import DecisionEngine

logger = logging.getLogger(__name__)


class Executor:
    """
    The Bot class is the main entry point for the botting framework.
    It is responsible for packaging all actions received from Bot Monitors (child processes) into a shared queue.
    It is also responsible for creating and cancelling tasks in the shared queue.
    Each Bot instance furthers has a listening loop that listens for actions from the Bot Monitor, which they then put
    into the shared queue (across all Bots).
    """

    blocker: asyncio.Event = asyncio.Event()
    logging_queue: multiprocessing.Queue
    all_bots: list["Executor"] = []

    def __init__(self, engine: type["DecisionEngine"], ign: str) -> None:
        self.engine = engine
        self.ign = ign
        self.handle = client_handler.get_client_handle(
            self.ign, ign_finder=engine.ign_finder
        )

        self.bot_side, self.monitoring_side = multiprocessing.Pipe()
        self.rotation_locks = [
            multiprocessing.Lock() for _ in range(5)  # TODO - Make this dynamic
        ]  # Used to manage when map rotation can be enqueued
        self.action_lock = (
            asyncio.Lock()
        )  # Used to manage multiple tasks being enqueued at the same time for a single bot
        self.update_bot_list(self)

        self.monitoring_process: multiprocessing.Process | None = None
        self.main_task: asyncio.Task | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        async with asyncio.TaskGroup() as tg:
            for bot in cls.all_bots:
                bot.main_task = tg.create_task(bot.engine_listener(), name=repr(bot))
                logger.info(f"Created task {bot.main_task.get_name()}.")

    @classmethod
    def cancel_all(cls):
        for bot in cls.all_bots:
            bot.bot_side.send(None)

    def create_task(self, queue_item: QueueAction) -> asyncio.Task:
        """
        Wrapper around asyncio.create_task which also handles task priority and cancellations.
        It defines how QueueAction objects are converted into asyncio.Task objects and interact with each other.

        Explanations: Tasks are created from QueueAction objects. They also contain a reference
        to the QueueAction object that created them. This is done so that when a task is cancelled,
        the QueueAction object can be re-queued into the shared queue.
        :param queue_item: The QueueAction object to be converted into a task and run asynchronously.
        :return: None
        """

        # Wrap the action to ensure it is not interfering with other actions from the same bot.
        queue_item.action = self._wrap_action(queue_item.action)

        new_task = asyncio.create_task(queue_item.action(), name=queue_item.identifier)
        new_task.add_done_callback(self._exception_handler)

        new_task.is_in_queue = True
        if queue_item.lock_id is not None:
            new_task.lock_id = queue_item.lock_id
            new_task.add_done_callback(self._rotation_callback)

        if queue_item.update_game_data is not None:
            new_task.add_done_callback(
                partial(self._send_update_signal_callback, queue_item.update_game_data)
            )

        # Add the original QueueAction into the task for re-queuing purposes.
        new_task.action = queue_item.action
        new_task.priority = queue_item.priority
        new_task.is_cancellable = queue_item.is_cancellable

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
    def update_logging_queue(cls, logging_queue: multiprocessing.Queue) -> None:
        """Updates the logging queue for all bots."""
        cls.logging_queue = logging_queue

    @classmethod
    def update_bot_list(cls, bot: "Executor") -> None:
        """Inserts newly created bot into the bot list."""
        cls.all_bots.append(bot)

    def _exception_handler(self, fut):
        try:
            if fut.exception() is not None:
                logger.exception(f"Exception occurred in task {fut.get_name()}.")
                self.cancel_all()
        except asyncio.CancelledError:
            pass

        except Exception as e:
            self.cancel_all()
            raise e

    def set_monitoring_process(self) -> None:
        assert (
            self.logging_queue is not None
        ), "Logging queue must be set before setting monitoring process."
        self.monitoring_process = multiprocessing.Process(
            target=self.engine.start_monitoring,
            name=f"{self} Monitoring",
            args=(self, Executor.logging_queue),
        )

    def _rotation_callback(self, fut):
        """Callback to use on map rotation actions if they need to acquire lock before executing."""
        self.rotation_locks[fut.lock_id].release()
        if fut.cancelled():
            logger.debug(f"Rotation Lock {fut.lock_id} released on {self} through callback. {fut.get_name()} is Cancelled.")
        else:
            logger.debug(f"Rotation Lock {fut.lock_id} released on {self} through callback. {fut.get_name()} is Done.")

    def _send_update_signal_callback(self, signal: tuple[str], fut):
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

    async def engine_listener(self) -> None:
        """
        Main Process task.
        Retrieves queue items from the monitoring loop (child process) and adds the item into the shared asynchronous queue.
        :return: None
        """
        while True:
            await self.blocker.wait()  # Blocks all Bots until a task clears the blocker. Used for Stopping/Pausing all bots through user-request from discord.

            if await asyncio.to_thread(self.bot_side.poll):
                queue_item: QueueAction = self.bot_side.recv()

                if queue_item is None:
                    logger.debug(
                        f"Received None from {self} monitoring process. Exiting."
                    )
                    self.cancel_all()
                    break

                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                new_task = self.create_task(queue_item)
                logger.debug(f"Created task {new_task.get_name()}.")

                if len(asyncio.all_tasks()) > 15:
                    logger.warning(
                        f"Number of tasks in the event loop is {len(asyncio.all_tasks())}."
                    )
