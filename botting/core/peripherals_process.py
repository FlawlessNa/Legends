from __future__ import annotations

import asyncio
import logging
import multiprocessing.connection
from typing import TYPE_CHECKING, Any

from botting.communications import DiscordIO
from botting.screen_recorder import Recorder
from botting.utilities import (
    exit_with_parent,
    install_loop_diagnostics,
    setup_child_proc_logging,
)

from .action_data import ActionRequest

if TYPE_CHECKING:
    from botting.communications import BaseParser

logger = logging.getLogger(__name__)


async def drain_pipe(pipe: multiprocessing.connection.Connection) -> None:
    """
    Child Process task standing in for the Discord relay when Discord is off.

    Reads what Main Process sends for Discord, and drops it: a full pipe would
    block the sender, and nothing here may reach Discord. Ends on the ``None``
    that means the Session is shutting down.
    :param pipe: The Peripherals end of the pipe to Main Process.
    """
    dropped = 0
    while True:
        if await asyncio.to_thread(pipe.poll, 0.1):
            if pipe.recv() is None:
                break
            dropped += 1
            if dropped == 1:
                logger.info("Discord is off: messages for it are dropped.")


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

    def __init__(
        self,
        queue: multiprocessing.Queue,
        parser: type[BaseParser],
        recording_section: str = "DEFAULT",
        discord: bool = True,
    ) -> None:
        """
        :param recording_section: The ``recordings.ini`` section the Recorder reads.
        :param discord: Whether to connect to Discord. ``False`` runs the Session
            without it: no client is built, no token is read, and every message
            meant for Discord is dropped, so the Session can post nowhere.
        """
        self.discord = discord
        self.log_queue = queue
        self.recording_section = recording_section
        self.process: multiprocessing.Process | None = None
        self.pipe_main_proc, self.pipe_spawned_proc = multiprocessing.Pipe()
        # PipeConnection vs Connection: typeshed types Windows' Pipe() ends as
        # PipeConnection; the parser annotates Connection.
        self.discord_parser = parser(self.pipe_main_proc)  # pyright: ignore[reportArgumentType]
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

        assert self.process is not None, "start() runs before kill()"
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

    def _dispatch_to_engines(self, action: object) -> None:
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
        exit_with_parent()

        asyncio.run(self._launch_tasks())

    async def _launch_tasks(self) -> None:
        """
        Child Process. Runs all tasks until the first one completes/cancels.
        Then cancels all other tasks.
        :return:
        """
        install_loop_diagnostics()
        recorder = Recorder(section=self.recording_section)
        tasks = [asyncio.create_task(recorder.start(), name="Screen Recorder")]
        if self.discord:
            discord_io = DiscordIO(self.pipe_spawned_proc)  # pyright: ignore[reportArgumentType]
            tasks.append(
                asyncio.create_task(
                    discord_io.relay_main_to_disc(), name="Discord Relay"
                )
            )
            tasks.append(
                asyncio.create_task(
                    discord_io.start(discord_io.config["DEFAULT"]["DISCORD_TOKEN"]),
                    name="Discord I/O",
                )
            )
        else:
            tasks.append(
                asyncio.create_task(
                    drain_pipe(self.pipe_spawned_proc),  # pyright: ignore[reportArgumentType]
                    name="Discord Off",
                )
            )

        task_done, task_pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
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
            logger.error("Task %s raised.", task.get_name(), exc_info=task.exception())
        if failures:
            first = failures[0].exception()
            assert first is not None, "failures holds only tasks that raised"
            raise first
