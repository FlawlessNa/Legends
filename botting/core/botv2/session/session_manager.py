import asyncio
import logging
import logging.handlers
import multiprocessing.connection

from typing import Self

from botting.core.botv2.engine_listener import EngineListener
from botting.core.botv2.monitor import Monitor

from botting.core.botv2.tasks.async_task_manager import AsyncTaskManager
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

    logging_queue = multiprocessing.Queue()

    def __init__(self, *engines: list[Monitor]) -> None:
        self.engines: tuple = engines
        self.task_manager = AsyncTaskManager()
        self.peripherals = PeripheralsProcess(self.logging_queue)

        self.log_receiver = logging.handlers.QueueListener(
            self.logging_queue, *logger.parent.handlers, respect_handler_level=True
        )
        self.listeners = []
        self.peripherals_listener = self.peripherals_process = None

    def __enter__(self) -> Self:
        self.peripherals.start()
        # self._launch_all_engines()
        self.log_receiver.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Whenever the context manager is exited, that means the Event loop's execution
        has halted, for whatever reason. In such a case, all EngineListeners are already
        stopped. Assuming the Engines handle their own clean-up,
        the remaining things left to do is to stop the peripherals and stop the log
        listener.
        :param exc_type: Exception Class.
        :param exc_val: Exception Value (instance).
        :param exc_tb: Exception Traceback.
        :return: None
        """
        self.peripherals.kill()
        logger.debug("Stopping Log listener")
        logger.info("SessionManager exited.")
        self.log_receiver.stop()

        if exc_type is not None:
            # Normally, each Engine should handle their own clean-up.
            # However, EngineListeners may not be able to handle their own clean-up??
            breakpoint()

    async def start(self):
        logger.info(f"Starting {len(self.engines)} Processes.")
        for lst_monitor in self.engines:
            logger.info(f"Launching Engine{lst_monitor}")

        try:
            await self._launch_all_listeners()
        finally:
            logger.info(
                "All bots have been stopped. Session is about to exit."
            )

    def _launch_all_engines(self) -> None:
        raise NotImplementedError

    async def _launch_all_listeners(self) -> None:
        """
        Launch all Engine Listeners and the Discord Listener.
        :return:
        """
        async with asyncio.TaskGroup() as tg:
            self.discord_listener = tg.create_task(
                self._relay_disc_to_main(), name="Discord Listener"
            )
            for engine in self.engines:
                listener = EngineListener(engine, self.pipe_to_peripherals)
                self.listeners.append(listener)
                listener.task = tg.create_task(listener.start(), name=repr(listener))
                logger.info(f"Created task {listener.task.get_name()}.")

    async def _relay_disc_to_main(self) -> None:
        raise NotImplementedError
