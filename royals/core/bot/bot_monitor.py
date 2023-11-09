import logging
import time

from .bot import Bot
from royals.utilities import ChildProcess
import multiprocessing

logger = logging.getLogger(__name__)


class BotMonitor(ChildProcess):
    def __init__(self, bot: Bot) -> None:
        super().__init__(bot.monitoring_side)
        self.source = repr(bot)
        self.monitoring_generators = bot.items_to_monitor
        self.map_rotation_generator = bot.next_map_rotation
        self.rotation_lock = bot.rotation_lock

    def start(self) -> None:
        """
        There are two types of generators that are monitored:
        1. Generators that are used to monitor the game state (potions, pet food, inventories, chat feed, proper map, etc).
        2. Generators that are used to determine the next map rotation.
        On every iteration, all generators from 1. are checked once.
        Then, the map rotation generator is checked whenever the bot is ready to perform an action related to map rotation.
        :return: None
        """
        try:
            generators = [
                gen() for gen in self.monitoring_generators(self.pipe_end)
            ]  # Instantiate all generators
            map_rotation = self.map_rotation_generator(self.pipe_end)()

            while True:
                # If main process sends None, it means we are exiting.
                if self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        break

                before = time.time()
                for check in generators:
                    next(check)
                # logger.debug(
                #     f"Time taken to execute all checks for {repr(self.source)}: {time.time() - before}"
                # )

                if self.rotation_lock.acquire(block=False):
                    logger.debug(
                        f"Acquired lock for {self.source} map rotation. Calling next rotation"
                    )
                    next(map_rotation)

        except Exception as e:
            raise

        finally:
            if not self.pipe_end.closed:
                self.pipe_end.send(None)
                self.pipe_end.close()

    @staticmethod
    def start_monitoring(
        bot: "Bot",
        log_queue: multiprocessing.Queue,
    ):
        """
        Starts the monitoring process by creating a BotMonitor instance (within child process) and then call its start() method.
        :param bot: The Bot instance (living in the main process) that is being monitored.
        :param log_queue: The logging queue that is used to send logs from the child process to the main process.
        :return:
        """
        ChildProcess.set_log_queue(log_queue)
        monitor = BotMonitor(bot)
        monitor.start()
