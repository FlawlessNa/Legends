import logging
import multiprocessing

from .executor import Executor

logger = logging.getLogger(__name__)


class BotLauncher:
    """
    Launcher class for all Bots.
    A single, shared asynchronous queue (class attribute) is used to schedule all Bots.
    This ensures that no two Bots are running in parallel, which would be suspicious.
    Instead of true parallelism, this fully leverages cooperative multitasking.
    Additionally, it defines synchronization primitives that can be used by all bots as well.
    """

    def __init__(self, logging_queue: multiprocessing.Queue) -> None:
        self.logging_queue = logging_queue

    def __enter__(self) -> None:
        for bot in Executor.all_bots:
            bot.set_monitoring_process()
            bot.monitoring_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for bot in Executor.all_bots:
            bot.bot_side.send(None)
            bot.bot_side.close()
            logger.debug(f"Sent stop signal to {bot} monitoring process")
            bot.monitoring_process.join()
            logger.debug(f"Joined {bot} monitoring process")
            logger.debug(f"Stopping {bot} main task")
            bot.main_task.cancel()
        logger.info(f"BotLauncher exited.")
