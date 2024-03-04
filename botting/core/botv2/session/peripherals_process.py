import asyncio
import logging
import multiprocessing.connection

from botting.screen_recorder import Recorder
from botting.core.communications.discord_comm import DiscordIO
from botting.utilities import setup_child_proc_logging

logger = logging.getLogger(__name__)


class PeripheralsProcess:
    """
    Lives in MainProcess.
    Used to spawn a new process to handle all peripherals tasks asynchronously.
    These tasks currently include:
    - Screen Recorder
    - Discord I/O (Relaying messages to and from the main process)
    """

    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.log_queue = queue
        self.process = None
        self.pipe_main_proc, self.pipe_spawned_proc = multiprocessing.Pipe()

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
        :return:
        """
        self.pipe_main_proc.send(None)
        self.pipe_main_proc.close()
        logger.debug("Sent stop signal to Peripherals process.")
        self.process.join()
        logger.info(f"Peripherals process exited.")

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
