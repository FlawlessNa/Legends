import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection

from typing import Self

from royals.screen_recorder import Recorder
from .discord_comm import DiscordComm
from .bot import Bot


logger = logging.getLogger(__name__)


class SessionManager:
    """
    Entry point to launch any Bot.
    The Manager will handle the following:
        - Establish Discord communications. While discord API is already asynchronous, we want to ensure that the Bot is not blocked by any Discord-related actions.
            Therefore, we launch a separate Process to handle Discord communications.
        - Launch an independent multiprocessing.Process to handle the screen recording. Recording is CPU-intensive and should not be done in the same process as the Bot.
        - Schedule each Bot as tasks to be executed in a single asyncio loop. This ensures no actions are executed in parallel, which would be suspicious.
        - Schedule a listener for Discord messages (received from the Discord child process). #TODO - Parse those message and send them to the appropriate Bot.
        - Schedule a listener for any log records from child processes.
        - Perform automatic clean-up as necessary. When the Bot is stopped, the Manager will ensure the screen recording is stopped and saved.
    """

    def __init__(self, *bots_to_launch: Bot) -> None:
        self.bots = bots_to_launch

        self.recorder_receiver, self.recorder_sender = multiprocessing.Pipe(
            duplex=False
        )  # One way communication
        (
            self.main_side,
            self.discord_side,
        ) = multiprocessing.Pipe()  # Two-way communication
        self.logging_queue = multiprocessing.Queue()
        self.log_listener = logging.handlers.QueueListener(
            self.logging_queue, *logger.parent.handlers, respect_handler_level=True
        )

    def __enter__(self) -> Self:
        """
        Setup all Bot tasks. Do not start.
        Setup Recorder process. Start Recorder process.
        Setup Discord process. Start Discord process.
        Start listening to any log records from those child processes.
        :return: self
        """
        self.recorder_process = multiprocessing.Process(
            target=self.create_recorder,
            name="Screen Recorder",
            args=(self.recorder_receiver, self.logging_queue),
        )
        self.recorder_process.start()
        self.discord_process = multiprocessing.Process(
            target=self.establish_discord_comm,
            name="Discord Communication",
            args=(self.discord_side, self.logging_queue),
        )
        self.discord_process.start()
        self.log_listener.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Whenever the context manager is exited, that means the asynchronous loop's execution has halted, for whatever reason. In such a case, all Bots are already stopped.
        Assuming the Bots handle their own clean-up, the only thing left to do is to stop the screen recording and save it. To do send, we send a signal to the isolated recording Process.
        :param exc_type: Exception Class.
        :param exc_val: Exception Value (instance).
        :param exc_tb: Exception Traceback.
        :return: None
        """
        self.recorder_sender.send(None)
        logger.debug("Sent stop signal to recorder process")

        self.main_side.send(None)
        logger.debug("Sent stop signal to discord process")
        self.recorder_process.join()
        self.discord_process.join()

        logger.debug("Stopping log listener")
        self.log_listener.stop()
        # asyncio.get_running_loop().stop()
        # asyncio.get_running_loop().close()

    @staticmethod
    def create_recorder(
        receiver: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
    ):
        recorder = Recorder(receiver, log_queue)
        recorder.start_recording()

    @staticmethod
    def establish_discord_comm(
        pipe_end: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
    ):
        discord_comm = DiscordComm(pipe_end, log_queue)
        asyncio.run(discord_comm.connect_and_listen())

    async def launch(self) -> None:
        logger.info(
            f'Launching {len(self.bots)} bots. The following bots will be launched: {", ".join([bot.__class__.__name__ for bot in self.bots])}'
        )
        asyncio.create_task(
            self.discord_process_listener(), name="Discord Message Parser"
        )
        async with asyncio.TaskGroup() as tg:
            for bot in self.bots:
                tg.create_task(bot.run(), name=bot.__class__.__name__)

    async def discord_process_listener(self) -> None:
        """
        #TODO - refactor at the appropriate package location
        # TODO - See if this blocks the main loop too much.
        :return: None
        """

        while True:
            if await asyncio.to_thread(self.main_side.poll):
                message = self.main_side.recv()
                if message.lower() == "kill":
                    logger.info("Received KILL signal from Discord. Stopping all bots.")
                    for task in asyncio.all_tasks():
                        if task.get_name() in [
                            bot.__class__.__name__ for bot in self.bots
                        ]:
                            task.cancel()
                    break
                logger.info(f"Received message from Discord: {message}")
        logger.debug("No more parsing messages from Discord.")
