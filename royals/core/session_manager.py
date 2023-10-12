import asyncio
import logging
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

    def __enter__(self) -> Self:
        """
        Setup all Bot tasks. Do not start.
        Setup Recorder process. Start Recorder process.
        Setup Discord process. Start Discord process.
        :return: self
        """
        self.recorder_process = multiprocessing.Process(
            target=self.create_recorder,
            name="Screen Recorder",
            args=(self.recorder_receiver,),
        )
        self.recorder_process.start()
        self.discord_process = multiprocessing.Process(
            target=self.establish_discord_comm,
            name="Discord Communication",
            args=(self.discord_side,),
        )
        self.discord_process.start()
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

    @staticmethod
    def create_recorder(receiver: multiprocessing.connection.Connection):
        recorder = Recorder(receiver)
        recorder.start_recording()

    @staticmethod
    def establish_discord_comm(pipe_end: multiprocessing.connection.Connection):
        discord_comm = DiscordComm(pipe_end)
        asyncio.run(discord_comm.connect_and_listen())

    async def launch(self) -> None:
        logger.info(
            f'Launching {len(self.bots)} bots. The following bots will be launched: {", ".join([bot.__class__.__name__ for bot in self.bots])}'
        )
        async with asyncio.TaskGroup() as tg:
            for bot in self.bots:
                tg.create_task(bot.run(), name=bot.__class__.__name__)
