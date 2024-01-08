import multiprocessing
import time

from abc import ABC, abstractmethod

from .decision_generator import DecisionGenerator
from .executor import Executor
from botting.core.bot.game_data import GameData
from botting.utilities import ChildProcess


class DecisionEngine(ChildProcess, ABC):
    ign_finder: callable  # Function that returns the handle of a client given its IGN. Defined in child classes.

    def __init__(
        self, logging_queue: multiprocessing.Queue, bot: Executor, *args, **kwargs
    ) -> None:
        super().__init__(logging_queue, bot.monitoring_side)
        self.rotation_lock = bot.rotation_lock
        self.source = repr(bot)
        self.handle = bot.handle
        self.ign = bot.ign

    @property
    @abstractmethod
    def game_data(self) -> GameData:
        """
        Child instances should store in this property the game data that is being monitored.
        :return: Game data.
        """
        pass

    @abstractmethod
    def items_to_monitor(self) -> list[DecisionGenerator]:
        """
        Child instances should store in this property a list of generators that are monitored by the monitoring loop (Child Process).
        Each item in this list is an iterator.
        At each loop iteration, next() is called on each item in this list, at which point the generator may send an action through the multiprocess pipe.
        :return: List of items to monitor.
        """
        pass

    @abstractmethod
    def next_map_rotation(self) -> list[DecisionGenerator]:
        """
        Same behavior as items_to_monitor(), but the generators in this list are used to determine the next map rotation.
        :return:
        """
        pass

    @abstractmethod
    def anti_detection_checks(self) -> list[DecisionGenerator]:
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
            anti_detection = [
                gen() for gen in self.anti_detection_checks()
            ]  # Instantiate all anti-detection checks generators

            while True:
                # If main process sends None, it means we are exiting.
                while self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        return
                    elif isinstance(signal, dict):
                        self.game_data.update(**signal)
                    else:
                        self.game_data.update(signal)

                for check in generators:
                    res = next(check)
                    if res:
                        self.pipe_end.send(res)

                if not self.game_data.block_rotation:
                    for rotation in map_rotation:
                        res = next(rotation)
                        if res:
                            self.pipe_end.send(res)

                for check in anti_detection:
                    res = next(check)
                    if res:
                        self.pipe_end.send(res)

                if self.game_data.shut_down_at is not None and time.perf_counter() > self.game_data.shut_down_at:
                    break

        except Exception as e:
            raise

        finally:
            if not self.pipe_end.closed:
                self.pipe_end.send(None)
                self.pipe_end.close()

    @staticmethod
    def start_monitoring(bot: "Executor", log_queue: multiprocessing.Queue, **kwargs):
        """
        The only BotMonitor method created in Main Process. It is set up into a mp.Process and started as a child from there.
        Starts the monitoring process by creating a BotMonitor instance (within child process) and then call its start() method.
        :param bot: The Bot instance (living in the main process) that is being monitored.
        :param log_queue: The logging queue that is used to send logs from the child process to the main process.
        :return:
        """
        monitor = bot.engine(log_queue, bot, **kwargs)
        monitor.start()
