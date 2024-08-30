import asyncio
import logging
import logging.handlers
import multiprocessing.connection

from typing import Self

from .async_task_manager import AsyncTaskManager
from .bot import Bot
from .engine import Engine
from .peripherals_process import PeripheralsProcess
from botting.communications import BaseParser
from botting.controller import release_all

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.INFO


class SessionManager:
    """
    Lives in MainProcess.
    Responsible to gather all relevant features and classes to create a Session.
    Those currently include:
    - Engine (and EngineListener)
    - PeripheralProcess (Screen Recorder and Discord I/O)
    - LogHandler
    - TaskManager
    """

    def __init__(self, discord_parser: type[BaseParser]) -> None:
        """
        Creates all necessary objects to start a new Session.
        :param discord_parser: A callable that parses discord message and returns
        ActionRequests.
        """
        # Create a Manager Process to share data between processes.
        self.process_manager = multiprocessing.Manager()
        self.metadata = self.process_manager.dict(
            logging_queue=self.process_manager.Queue(),
            proxy_request=self.process_manager.Condition(),
            # _disabled=self.process_manager.dict(),
        )
        self.metadata["ignored_keys"] = set(self.metadata.keys()).union(
            {"ignored_keys"}
        )

        self.peripherals = PeripheralsProcess(
            self.metadata["logging_queue"], discord_parser
        )
        self.task_manager = AsyncTaskManager(
            discord_pipe=self.peripherals.pipe_main_proc,
        )

        self.log_receiver = logging.handlers.QueueListener(
            self.metadata["logging_queue"],
            *logger.parent.handlers,
            respect_handler_level=True,
        )

        self.engines: list[multiprocessing.Process] = []
        self.listeners: list[asyncio.Task] = []
        self.discord_listener: asyncio.Task | None = None
        self.proxy_listener: asyncio.Task | None = None
        self.management_task: asyncio.Task | None = None
        self.main_bot = None
        self.bots = []
        self.barrier = None  # Used to start all tasks simultaneously.

    def __enter__(self) -> Self:
        """
        Spawns all necessary child processes and starts them.
        Both the Peripherals process and its listener are started.
        :return:
        """
        self.log_receiver.start()
        self.peripherals.start()
        self.discord_listener = asyncio.create_task(
            self.peripherals.peripherals_listener(self.task_manager.queue),
            name="Discord Listener",
        )
        self.proxy_listener = asyncio.create_task(
            self._monitor_proxy(), name="Proxy Listener"
        )
        self.management_task = asyncio.create_task(
            self.task_manager.start(), name="Task Manager"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Whenever the context manager is exited, that means the Event loop's execution
        has halted, for whatever reason. In such a case, all Engine Listeners are
        already stopped. Assuming the Engines handle their own clean-up,
        the remaining things left to do is to stop the peripherals and stop the log
        listener.
        :param exc_type: Exception Class.
        :param exc_val: Exception Value (instance).
        :param exc_tb: Exception Traceback.
        :return: None
        """
        self.peripherals.kill()
        self.discord_listener.cancel("SessionManager exited.")
        logger.debug("Stopping Log listener.")
        logger.info("SessionManager exited.")
        self.log_receiver.stop()

        for engine in self.engines:
            engine.join(timeout=5)
            if engine.is_alive():
                engine.terminate()
            logger.info(f"Engine {engine.name} has been stopped.")

        for bot in self.bots:
            release_all(bot.get_handle_from_ign(bot.ign))

        if exc_type is not None:
            # Normally, each Engine should handle their own clean-up.
            # However, Listeners may not be able to handle their own clean-up??
            raise exc_val

    async def launch(self, *grouped_bots: list[Bot]) -> None:
        """
        Launch all bots. The "Main" bot is ALWAYS set to the first bot within first group
        :param grouped_bots: Each group is launched in a single Engine.
        :return:
        """
        self.main_bot = grouped_bots[0][0]
        self.barrier = self.process_manager.Barrier(
            sum(len(group) for group in grouped_bots)
        )
        for group in grouped_bots:
            self.bots.extend(group)
            engine_side, listener_side = multiprocessing.Pipe()
            engine_proc = Engine.start(engine_side, self.metadata, group, self.barrier)
            engine_listener = Engine.listener(
                listener_side,
                self.task_manager.queue,
                engine_proc,
                self.peripherals.pipe_main_proc,
            )
            self.engines.append(engine_proc)
            self.listeners.append(engine_listener)
        t_done, t_pending = await asyncio.wait(
            self.listeners
            + [self.discord_listener, self.proxy_listener, self.management_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        t_done = t_done.pop()

        for task in t_pending:
            logger.info(f"Cancelling task {task.get_name()}.")
            task.cancel()

        if t_done.exception():
            self.peripherals.pipe_main_proc.send(f"Error: {t_done.exception()}")
            raise t_done.exception()
        logger.info("All bots have been stopped. Session is about to exit.")

    async def _monitor_proxy(self) -> None:
        """
        Monitor the proxy request queue.
        :return:
        """
        notifier = self.metadata["proxy_request"]

        def _single_cycle(cond):
            with cond:  # Acquire the underlying Lock
                while not cond.wait(timeout=1):  # Release and wait for notification
                    if self.proxy_listener.cancelling():
                        return
                # Reaching here, we've reacquired the Lock after being notified
                key = next(
                    key
                    for key in self.metadata.keys()
                    if key not in self.metadata["ignored_keys"]
                )
                type_, args, kwargs = self.metadata[key]
                logger.log(LOG_LEVEL, f"Request received from {key} for {type_}.")
                self.metadata[key] = getattr(self.process_manager, type_)(
                    *args, **kwargs
                )
                cond.notify_all()  # The proxy request has been processed, notify waiter

        while True:
            await asyncio.to_thread(_single_cycle, notifier)
