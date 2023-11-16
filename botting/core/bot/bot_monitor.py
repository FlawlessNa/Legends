import logging
import multiprocessing

from abc import ABC, abstractmethod

from .bot import Bot, GameData
from botting.utilities import ChildProcess

logger = logging.getLogger(__name__)


class BotMonitor(ChildProcess, ABC):
    def __init__(self, bot: Bot) -> None:
        super().__init__(bot.monitoring_side)
        self.source = repr(bot)
        self.watched_bot = bot
        self.game_data: GameData = bot.game_data

    @abstractmethod
    def items_to_monitor(self) -> list[callable]:
        """
        Child instances should store in this property a list of generators that are monitored by the monitoring loop (Child Process).
        Each item in this list is an iterator.
        At each loop iteration, next() is called on each item in this list, at which point the generator may send an action through the multiprocess pipe.
        :return: List of items to monitor.
        """
        pass

    @abstractmethod
    def next_map_rotation(self) -> list[callable]:
        """
        Same behavior as items_to_monitor(), but the generators in this list are used to determine the next map rotation.
        :return:
        """
        pass

    def start(self) -> None:
        """
        There are two types of generators that are monitored:
        1. Generators that are used to monitor the game state (potions, pet food, inventories, chat feed, proper map, etc).
        2. Generators that are used to determine the next map rotation.
        On every iteration, we start by checking if the main process has sent anything through the pipe.
        If so, we update the game data with the new information.
        Then, all generators from 1. are checked once.
        Lastly, all generators from 2. are checked once.
        :return: None
        """
        try:
            generators = [
                gen() for gen in self.items_to_monitor()
            ]  # Instantiate all checks generators
            map_rotation = [
                gen() for gen in self.next_map_rotation()
            ]  # Instantiate all map rotation generators

            while True:
                # If main process sends None, it means we are exiting.
                while self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        break
                    self.game_data.update(signal)

                for check in generators:
                    next(check)

                for rotation in map_rotation:
                    next(rotation)

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
        The only BotMonitor method created in Main Process. It is set up into a mp.Process and started as a child from there.
        Starts the monitoring process by creating a BotMonitor instance (within child process) and then call its start() method.
        :param bot: The Bot instance (living in the main process) that is being monitored.
        :param log_queue: The logging queue that is used to send logs from the child process to the main process.
        :return:
        """
        ChildProcess.set_log_queue(log_queue)
        monitor = bot.monitor(bot)
        monitor.start()
