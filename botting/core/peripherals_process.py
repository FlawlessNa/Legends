import asyncio
import logging
import multiprocessing.connection
from typing import Any
from botting.screen_recorder import Recorder
from botting.communications import DiscordIO, BaseParser
from botting.utilities import setup_child_proc_logging

from .action_data import ActionRequest

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
        logger.info(f"Peripherals process exited.")

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
            t_done = task_done.pop()

            logger.info(f"Task {t_done.get_name()} has exited.")
            for task in task_pending:
                logger.info(f"Cancelling task {task.get_name()}.")
                task.cancel()

            if t_done.exception():
                raise t_done.exception()

        asyncio.run(_launch_tasks())
