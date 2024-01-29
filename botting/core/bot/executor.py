import asyncio
import logging
import multiprocessing.connection

from functools import partial
from typing import TYPE_CHECKING

from .pipe_signals import QueueAction
from botting.utilities import client_handler

if TYPE_CHECKING:
    from .decision_engine import DecisionEngine

logger = logging.getLogger(__name__)


class Executor:
    """
    The Bot class is the main entry point for the botting framework.
    It is responsible for monitoring and packaging all actions received from
    DecisionEngines (child processes) and schedule into a shared asynchronous queue.
    It is also responsible for managing tasks scheduled into the queue after creation.
    It is also responsible for listening to the discord process and see if any actions
    are requested by user.
    """

    blocker: asyncio.Event = asyncio.Event()
    logging_queue: multiprocessing.Queue  # Log records sent from child processes
    discord_pipe: multiprocessing.connection.Connection
    discord_listener: asyncio.Task  # Class attribute to keep track of discord messages
    discord_parser: callable  # Defines how to interpret discord messages
    all_bots: list["Executor"] = []

    def __init__(self, engine: type["DecisionEngine"], ign: str, **kwargs) -> None:
        self.engine = engine
        self.engine_kwargs = kwargs
        self.ign = ign
        self.handle = client_handler.get_client_handle(
            self.ign, ign_finder=engine.ign_finder
        )

        self.bot_side, self.monitoring_side = multiprocessing.Pipe()

        # Single Rotation Lock by Bot - Prevents simultaneous rotation actions
        self.rotation_lock = multiprocessing.Lock()

        # Single Action Lock by Bot - Prevents conflicting actions from being executed
        # simultaneously
        self.action_lock = asyncio.Lock()

        self.update_bot_list(self)

        self.monitoring_process: multiprocessing.Process | None = None
        self.main_task: asyncio.Task | None = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.ign}]"

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        async with asyncio.TaskGroup() as tg:
            cls.discord_listener = tg.create_task(
                cls.relay_disc_to_main(), name="Discord Listener"
            )
            for bot in cls.all_bots:
                bot.main_task = tg.create_task(bot.engine_listener(), name=repr(bot))
                logger.info(f"Created task {bot.main_task.get_name()}.")

    @classmethod
    def cancel_all(cls):
        for bot in cls.all_bots:
            bot.bot_side.send(None)
        cls.discord_pipe.send(None)
        cls.discord_listener.cancel()

    @classmethod
    async def relay_disc_to_main(cls) -> None:
        """
        TODO - Refactor to make it work with multiple executors simultaneously.
        TODO - Requires improved parsing.
        Main Process task.
        Responsible for listening to the discord process and see if any actions
        are requested by discord user.
        It then performs those actions.
        :return: None
        """
        while True:
            if await asyncio.to_thread(cls.discord_pipe.poll):
                message: str = cls.discord_pipe.recv()
                action: QueueAction = cls.discord_parser(message, cls.all_bots)
                if action is None:
                    logger.info(f"Received {message} from discord process. Exiting.")
                    cls.cancel_all()
                    cls.discord_pipe.send(None)
                    break
                else:
                    logger.info(
                        f"Performing action {action} as requested by discord user."
                    )
                    new_task = cls.all_bots[0].create_task(action)

    def create_task(self, queue_item: QueueAction) -> asyncio.Task:
        """
        Wrapper around asyncio.create_task which also handles task priority and
        cancellations. It defines how QueueAction objects are converted into
        asyncio.Task objects and interact with each other.

        :param queue_item: The QueueAction object to be converted into a task and ran
        asynchronously.
        :return:
        """
        if queue_item.action is None:
            queue_item.action = partial(asyncio.sleep, 0)

        # Ensures action is not interfering with other actions from the same bot.
        queue_item.action = self._wrap_action(queue_item.action)

        # Callbacks are triggered upon completion OR cancellation of the task.
        new_task = asyncio.create_task(queue_item.action(), name=queue_item.identifier)
        new_task.add_done_callback(self._exception_handler)

        # Custom attributes used to manage cancellations properly.
        new_task.is_in_queue = True
        new_task.priority = queue_item.priority
        new_task.is_cancellable = queue_item.is_cancellable

        if queue_item.release_lock_on_callback:
            new_task.add_done_callback(self._rotation_callback)

        if queue_item.update_generators is not None:
            new_task.add_done_callback(
                partial(self._send_update_signal_callback, queue_item.update_generators)
            )

        # TODO - Implement if every needed. Those callbacks would execute in Main
        if queue_item.callbacks:
            for callback in queue_item.callbacks:
                new_task.add_done_callback(callback)

        # Add the original QueueAction object into the task for logging purposes.
        new_task.action = queue_item.action

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
                    id_ = queue_item.identifier
                    name = task.get_name()
                    logger.debug(
                        f"{id_} has priority over task {name}. Cancelling {name}."
                    )
                    task.cancel()

        if queue_item.user_message is not None:
            logger.info(f"Sending message towards Discord Process")
            for msg in queue_item.user_message:
                self.discord_pipe.send(msg)

        return new_task

    @classmethod
    def update_logging_queue(cls, logging_queue: multiprocessing.Queue) -> None:
        """Updates the logging queue for all bots."""
        cls.logging_queue = logging_queue

    @classmethod
    def update_discord_pipe(
        cls, discord_pipe: multiprocessing.connection.Connection
    ) -> None:
        """Updates the discord pipe for all bots."""
        cls.discord_pipe = discord_pipe

    @classmethod
    def update_bot_list(cls, bot: "Executor") -> None:
        """Inserts newly created bot into the bot list."""
        cls.all_bots.append(bot)

    @classmethod
    def update_discord_parser(cls, parser: callable) -> None:
        """Updates the message parser for all bots."""
        cls.discord_parser = parser

    @classmethod
    def _exception_handler(cls, fut):
        try:
            if fut.exception() is not None and not isinstance(
                fut.exception(), TimeoutError
            ):
                logger.exception(f"Exception occurred in task {fut.get_name()}.")
                cls.discord_pipe.send(f"Exception occurred in task {fut.get_name()}.")
                cls.cancel_all()
                raise fut.exception()
        except asyncio.CancelledError:
            pass

        except Exception as e:
            cls.discord_pipe.send(f"Exception occurred in task {fut.get_name()}.")
            cls.cancel_all()
            raise e

    def set_monitoring_process(self) -> None:
        assert (
            self.logging_queue is not None
        ), "Logging queue must be set before setting monitoring process."
        self.monitoring_process = multiprocessing.Process(
            target=self.engine.start_monitoring,
            name=f"{self} Monitoring",
            args=(self, Executor.logging_queue),
            kwargs=self.engine_kwargs,
        )

    def _rotation_callback(self, fut):
        """
        Callback to use on map rotation actions if they need to acquire lock before
        executing. In some cases, such as failsafe responses, the lock has not been
        acquired yet.
        For this reason, try to acquire the lock before releasing it.
        """
        self.rotation_lock.acquire(block=False)
        self.rotation_lock.release()
        if fut.cancelled():
            pass
            # logger.debug(
            #     f"Rotation Lock released on {self} through callback. {fut.get_name()} is Cancelled."
            # )
        else:
            pass
            # logger.debug(
            #     f"Rotation Lock released on {self} through callback. {fut.get_name()} is Done."
            # )

    def _send_update_signal_callback(self, signal: tuple[str] | dict, fut):
        """
        Callback to use on map rotation actions if they need to update game game_data.
        Sends a signal back to the Child process to appropriately update Game Data.
        This way, CPU-intensive resources are not consumed within the main process.
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
                # logger.debug(f"Action Lock acquired for {self} for {action}")
                await action()
            finally:
                self.action_lock.release()
                # logger.debug(f"Action Lock released for {self} for {action}")

        return _wrapper

    async def engine_listener(self) -> None:
        """
        Main Process task.
        Retrieves queue items from the monitoring loop (child process) and adds the item
        into the shared asynchronous queue.
        :return: None
        """
        while True:
            # Blocks all Bots until a task clears the blocker. CURRENTLY NOT USED.
            await self.blocker.wait()

            if await asyncio.to_thread(self.bot_side.poll):
                queue_item: QueueAction = self.bot_side.recv()

                if queue_item is None:
                    logger.debug(
                        f"Received None from {self} monitoring process. Exiting."
                    )
                    self.cancel_all()
                    break
                elif isinstance(queue_item, Exception):
                    logger.exception(
                        f"Exception occurred in {self} monitoring process. Exiting."
                    )
                    self.discord_pipe.send(
                        f"""
                    Source: Monitor of {self}
                    Exception: {queue_item}
                    """
                    )
                    self.cancel_all()
                    break

                logger.debug(f"Received {queue_item} from {self} monitoring process.")
                if queue_item.identifier in [
                    task.get_name() for task in asyncio.all_tasks()
                ]:
                    logger.warning(
                        f"Task {queue_item.identifier} already exists. Skipping."
                    )
                    continue

                new_task = self.create_task(queue_item)
                logger.debug(f"Created task {new_task.get_name()}.")

                if len(asyncio.all_tasks()) > 30:
                    for t in asyncio.all_tasks():
                        print(t)
                    logger.warning(
                        f"Nbr of tasks in the event loop is {len(asyncio.all_tasks())}."
                    )
