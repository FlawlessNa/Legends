import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection

from typing import Self

from royals.screen_recorder import RecorderLauncher
from .communications import DiscordLauncher
from .bot import Bot, BotLauncher


logger = logging.getLogger(__name__)


class SessionManager(BotLauncher, DiscordLauncher, RecorderLauncher):
    """
    Entry point to launch any Bot.
    The Manager will handle the following:
        - Establish Discord communications. While discord API is already asynchronous, we want to ensure that the Bot is not blocked by any Discord-related actions.
            Therefore, we launch a separate Process to handle Discord communications.
        - Launch an independent multiprocessing.Process to handle the screen recording. Recording is CPU-intensive and should not be done in the same process as the Bot.
        - Schedule each Bot as tasks to be executed in a single asyncio loop. This ensures no actions are executed in parallel, which would be suspicious.
        - Schedule a listener for Discord messages (received from the Discord child process).
        - Schedule a listener for any log records from child processes.
        - Perform automatic clean-up as necessary. When the Bot is stopped, the Manager will ensure the screen recording is stopped and saved.
    """
    logging_queue = multiprocessing.Queue()

    def __init__(self, *bots_to_launch: Bot) -> None:
        self.bots = bots_to_launch
        BotLauncher.__init__(self, self.logging_queue)
        DiscordLauncher.__init__(self, self.logging_queue)
        RecorderLauncher.__init__(self, self.logging_queue)
        self.log_listener = logging.handlers.QueueListener(
            self.logging_queue, *logger.parent.handlers, respect_handler_level=True
        )

    def __enter__(self) -> Self:
        """
        Setup all Bot tasks. Start Monitoring process on each.
        Setup Recorder process. Start Recorder process.
        Setup Discord process. Start Discord process.
        Start listening to any log records from those child processes.
        :return: self
        """
        BotLauncher.__enter__(self)
        DiscordLauncher.__enter__(self)
        RecorderLauncher.__enter__(self)
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
        BotLauncher.__exit__(self, exc_type, exc_val, exc_tb)
        DiscordLauncher.__exit__(self, exc_type, exc_val, exc_tb)
        RecorderLauncher.__exit__(self, exc_type, exc_val, exc_tb)

        logger.debug("Stopping Log listener")
        self.log_listener.stop()

        if exc_type is not None:
            # TODO - Perform "Bots" cleanup since an error occur. (e.g. close all open windows)
            pass

    async def launch(self) -> None:
        logger.info(
            f'Launching {len(self.bots)} bots. The following bots will be launched: {" ".join(repr(bot) for bot in self.bots)}'
        )
        try:
            await BotLauncher.run_all()
        finally:
            logger.info("All bots have been stopped. calling __exit__ on all launchers.")
