from __future__ import annotations

import asyncio
import logging
import logging.config
import logging.handlers
import multiprocessing.connection
from typing import TYPE_CHECKING, Self

from botting.controller import HeldKeysLedger, release_all
from botting.logging_config import PARENT_LOG, full_config, new_session_dir
from botting.telemetry import TELEMETRY_FILENAME, TelemetryHandler
from botting.utilities import install_loop_diagnostics

from .async_task_manager import AsyncTaskManager
from .bot import Bot
from .engine import Engine
from .peripherals_process import PeripheralsProcess

if TYPE_CHECKING:
    from botting.communications import BaseParser

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

    def __init__(
        self, discord_parser: type[BaseParser], *, debug: bool = False
    ) -> None:
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
            # Read by each Engine child to mirror this process' asyncio debug mode.
            # Set here, before ignored_keys is computed, so the proxy-request scan in
            # _monitor_proxy keeps skipping it.
            debug=debug,
        )
        self.metadata["ignored_keys"] = set(self.metadata.keys()).union(
            {"ignored_keys"}
        )
        self._debug = debug

        if not self._debug:
            self.peripherals = PeripheralsProcess(
                self.metadata["logging_queue"], discord_parser
            )
        else:
            from unittest.mock import AsyncMock, Mock

            async def _wait_forever(*args, **kwargs):
                await asyncio.Event().wait()

            self.peripherals = Mock()
            self.peripherals.peripherals_listener = AsyncMock(side_effect=_wait_forever)

        self.task_manager = AsyncTaskManager(
            discord_pipe=self.peripherals.pipe_main_proc,
        )

        # One Session, one directory - text logs and telemetry alike. Built here
        # rather than in __enter__ because the QueueListener below snapshots the
        # parent logger's handlers at construction: attach the sink after that
        # and every Telemetry Record emitted in a child process reaches nothing.
        self.session_dir = new_session_dir()

        # The handlers themselves: one file per Log Bucket, the combined
        # session.log, and the console. dictConfig *replaces* the parent
        # logger's handler list, so it has to run before the telemetry sink is
        # attached below - the other order would discard the sink.
        logging.config.dictConfig(full_config(self.session_dir))

        self.telemetry_handler = TelemetryHandler(self.session_dir / TELEMETRY_FILENAME)
        logging.getLogger(PARENT_LOG).addHandler(self.telemetry_handler)

        self.log_receiver = logging.handlers.QueueListener(
            self.metadata["logging_queue"],
            # Named explicitly rather than reached through `logger.parent`: this
            # module's parent resolves to `botting` only for as long as no
            # `botting.core` logger object exists, and the moment one does, the
            # listener would silently be built with zero handlers.
            *logging.getLogger(PARENT_LOG).handlers,
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
        # Session-start reconciliation: the Held-Keys Ledger starts empty, so sweep the
        # physical keyboard once to make that true - a previous Session may have died
        # with a key latched down.
        HeldKeysLedger.reset()
        release_all()
        install_loop_diagnostics(debug=self._debug)
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

        # After stop(), so records still in flight from a child process land in
        # the JSONL file rather than on a closed stream.
        logging.getLogger(PARENT_LOG).removeHandler(self.telemetry_handler)
        self.telemetry_handler.close()

        for engine in self.engines:
            engine.join(timeout=2)
            if engine.is_alive():
                engine.terminate()
            logger.info("Engine %s has been stopped.", engine.name)

        if not self._debug:
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
        self.peripherals.discord_parser.main_ign = self.main_bot.ign
        self.barrier = self.process_manager.Barrier(
            sum(len(group) for group in grouped_bots)
        )
        for group in grouped_bots:
            self.bots.extend(group)
            engine_side, listener_side = multiprocessing.Pipe()
            self.peripherals.engine_pipes.append(listener_side)
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

        for task in t_pending:
            logger.info("Cancelling task %s.", task.get_name())
            task.cancel()

        # Every member of the done set is inspected, not just one: tasks that complete
        # on the same loop iteration would otherwise have their exception retrieved by
        # nobody, which is how a Session dies with its cause missing from the log.
        failures = [
            task
            for task in t_done
            if not task.cancelled() and task.exception() is not None
        ]
        for task in failures:
            logger.error("Task %s raised.", task.get_name(), exc_info=task.exception())
            self.peripherals.pipe_main_proc.send(
                f"Error in {task.get_name()}: {task.exception()}"
            )
        if failures:
            raise failures[0].exception()
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
                logger.debug("Request received from %s for %s.", key, type_)
                self.metadata[key] = getattr(self.process_manager, type_)(
                    *args, **kwargs
                )
                cond.notify_all()  # The proxy request has been processed, notify waiter

        while True:
            await asyncio.to_thread(_single_cycle, notifier)
