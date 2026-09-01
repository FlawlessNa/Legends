from __future__ import annotations

import asyncio
import logging
import multiprocessing.connection
from typing import TYPE_CHECKING, Any

from botting.communications import DiscordIO
from botting.screen_recorder import Recorder
from botting.utilities import install_loop_diagnostics, setup_child_proc_logging

from .action_data import ActionRequest

if TYPE_CHECKING:
    from botting.communications import BaseParser

logger = logging.getLogger(__name__)


class PeripheralsProcess:
    """
    Lives in MainProcess.
    Used to spawn a new process to handle all peripherals tasks asynchronously.
    These tasks currently include:
    - Screen Recorder
    - Discord Relay (Relaying messages from MainProcess towards Discord)
    - Discord I/O (Sentinel that watches for message on specified discord channel and
        relays to MainProcess)
    """

    def __init__(self, queue: multiprocessing.Queue, parser: type[BaseParser]) -> None:
        self.log_queue = queue
        self.process = None
        self.pipe_main_proc, self.pipe_spawned_proc = multiprocessing.Pipe()
        self.discord_parser = parser(self.pipe_main_proc)
        self.engine_pipes: list[multiprocessing.connection.Connection] = []

    def start(self) -> None:
        """
        Called from the MainProcess.
        Spawns a new process to handle all peripherals tasks asynchronously.
        :return:
        """
        self.process = multiprocessing.Process(
            target=self._spawn_child,
            name="Peripherals",
        )
        self.process.start()

    def kill(self) -> None:
        """
        Called from the MainProcess.
        Sends a stop signal to the peripherals process and waits for it to exit.
        Cancels the listener task.
        :return:
        """
        if not self.pipe_main_proc.closed:
            self.pipe_main_proc.send(None)
            self.pipe_main_proc.close()
            logger.debug("Sent stop signal to Peripherals process.")

        self.process.join()
        logger.info("Peripherals process exited.")

    async def peripherals_listener(self, async_queue: asyncio.Queue) -> None:
        """
        Main Process task.
        Responsible for listening to the Peripherals discord pipe and see if any actions
        are requested by discord user.
        :return: None
        """
        try:
            while True:
                if await asyncio.to_thread(self.pipe_main_proc.poll):
                    message: str = self.pipe_main_proc.recv()
                    action: Any = self.discord_parser.parse_message(message)

                    if isinstance(action, ActionRequest):
                        await async_queue.put(action)
                    elif action is not None:
                        self._dispatch_to_engines(action)

        finally:
            if not self.pipe_main_proc.closed:
                logger.debug("Closing Main pipe to peripherals process.")
                self.pipe_main_proc.send(None)
                self.pipe_main_proc.close()
            async_queue.put_nowait(None)

    def _dispatch_to_engines(self, action: Any) -> None:
        """
        Main Process task.
        Dispatches the action to all engines.
        :param action: The action to dispatch.
        :return: None
        """
        for engine_pipe in self.engine_pipes:
            engine_pipe.send(action)

    def _spawn_child(self) -> None:
        """
        Child Process Entry Point.
        Creates all necessary peripherals and starts their tasks into an event loop.
        :return:
        """
        setup_child_proc_logging(self.log_queue)

        async def _launch_tasks():
            """
            Runs all tasks until the first one completes/cancels.
            Then cancels all other tasks.
            :return:
            """
            install_loop_diagnostics()
            recorder = Recorder()
            discord_io = DiscordIO(self.pipe_spawned_proc)

            task_recorder = asyncio.create_task(
                recorder.start(), name="Screen Recorder"
            )
            task_discord_relay = asyncio.create_task(
                discord_io.relay_main_to_disc(), name="Discord Relay"
            )
            task_discord_io = asyncio.create_task(
                discord_io.start(discord_io.config["DEFAULT"]["DISCORD_TOKEN"]),
                name="Discord I/O",
            )

            task_done, task_pending = await asyncio.wait(
                [task_recorder, task_discord_relay, task_discord_io],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in task_done:
                logger.info("Task %s has exited.", task.get_name())
            for task in task_pending:
                logger.info("Cancelling task %s.", task.get_name())
                task.cancel()

            # Same reasoning as the Engine and SessionManager wait sites: retrieve
            # every done task's exception, not just the first one popped.
            failures = [
                task
                for task in task_done
                if not task.cancelled() and task.exception() is not None
            ]
            for task in failures:
                logger.error(
                    "Task %s raised.", task.get_name(), exc_info=task.exception()
                )
            if failures:
                raise failures[0].exception()

        asyncio.run(_launch_tasks())
