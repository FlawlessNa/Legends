import asyncio
import logging
import logging.handlers
import multiprocessing.connection

from typing import Self

from .bot import Bot
from .engine import Engine
from .peripherals_process import PeripheralsProcess

logger = logging.getLogger(__name__)


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

    def __init__(self) -> None:
        """
        Creates all necessary objects to start a new Session.
        """
        # Create a Manager Process to share data between processes.
        self.manager = multiprocessing.Manager()
        self.metadata = self.manager.dict()
        # Add the logging queue to the metadata for convenience.
        self.metadata["Logging Queue"] = self.manager.Queue()

        self.peripherals = PeripheralsProcess(self.metadata["Logging Queue"])

        self.log_receiver = logging.handlers.QueueListener(
            self.metadata["Logging Queue"],
            *logger.parent.handlers,
            respect_handler_level=True,
        )

        self.async_queue = asyncio.Queue()
        self.engines: list[multiprocessing.Process] = []
        self.listeners: list[callable] = []
        self.discord_listener: asyncio.Task | None = None

    def __enter__(self) -> Self:
        """
        Spawns all necessary child processes and starts them.
        Both the Peripherals process and its listener are started.
        :return:
        """
        self.log_receiver.start()
        self.peripherals.start()
        self.discord_listener = asyncio.create_task(
            self.peripherals.peripherals_listener(self.async_queue),
            name="Discord Listener"
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
        self.discord_listener.cancel('SessionManager exited.')
        # self._kill_all_engines()
        logger.debug("Stopping Log listener")
        logger.info("SessionManager exited.")
        self.log_receiver.stop()

        if exc_type is not None:
            # Normally, each Engine should handle their own clean-up.
            # However, EngineListeners may not be able to handle their own clean-up??
            breakpoint()

    async def launch(self, *grouped_bots: list[Bot]) -> None:
        for group in grouped_bots:
            engine_side, listener_side = multiprocessing.Pipe()
            self.engines.append(Engine.start(engine_side, self.metadata, group))
            self.listeners.append(Engine.listener(listener_side, self.async_queue))
        await self._launch_all_listeners()

    def _kill_all_engines(self) -> None:
        raise NotImplementedError

    async def _launch_all_listeners(self) -> None:
        """
        Launch all Engine Listeners and the Discord Listener.
        :return:
        """
        logger.info(f"Launching {len(self.listeners)} Engine Listeners.")
        try:
            async with asyncio.TaskGroup() as tg:
                for listener in self.listeners:
                    listener.task = tg.create_task(
                        listener, name=repr(listener)
                    )
                    logger.info(f"Created task {listener.task.get_name()}.")
        finally:
            logger.info("All bots have been stopped. Session is about to exit.")
