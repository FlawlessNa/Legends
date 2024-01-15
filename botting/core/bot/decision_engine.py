import itertools
import multiprocessing

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
        Child instances should store in this property the game game_data that is being monitored.
        :return: Game game_data.
        """
        pass

    @property
    @abstractmethod
    def items_to_monitor(self) -> list[DecisionGenerator]:
        """
        Child instances should store in this property a list of generators that are monitored by the monitoring loop (Child Process).
        Each item in this list is an iterator.
        At each loop iteration, next() is called on each item in this list, at which point the generator may send an action through the multiprocess pipe.
        :return: List of items to monitor.
        """
        pass

    @property
    @abstractmethod
    def next_map_rotation(self) -> DecisionGenerator:
        """
        Same behavior as items_to_monitor(), but the generators in this list are used to determine the next map rotation.
        :return:
        """
        pass

    @property
    @abstractmethod
    def anti_detection_checks(self) -> list[DecisionGenerator]:
        pass

    def start(self) -> None:
        """
        There are two types of generators that are monitored:
        1. Generators that are used to monitor the game state (potions, pet food, inventories, chat feed, proper map, etc).
        2. Generators that are used to determine the next map rotation.
        On every iteration, we start by checking if the main process has sent anything through the pipe.
        If so, we update the game game_data with the new information.
        Then, all generators from 1. are checked once.
        Lastly, all generators from 2. are checked once.
        :return: None
        """
        monitors_generators = self.items_to_monitor
        rotation_generator = self.next_map_rotation
        anti_detection_generators = self.anti_detection_checks

        for decision_generator in itertools.chain(
            monitors_generators, anti_detection_generators, [rotation_generator]
        ):
            self.game_data.update(*decision_generator.data_requirements)
            self.game_data.create_blocker(
                repr(decision_generator), decision_generator.generator_type
            )

        try:
            generators = [
                iter(gen) for gen in monitors_generators
            ]  # Instantiate all checks generators

            map_rotation = iter(rotation_generator)

            anti_detection = [
                iter(gen) for gen in anti_detection_generators
            ]  # Instantiate all anti-detection checks generators

            while True:
                # If main process sends None, it means we are exiting.
                while self.pipe_end.poll():
                    signal = self.pipe_end.recv()
                    if signal is None:
                        return

                    # If main process sends anything else, update game data
                    elif isinstance(signal, dict):
                        self.game_data.update(**signal)
                    else:
                        self.game_data.update(signal)

                for check in generators:
                    res = next(check)
                    if res:
                        self.pipe_end.send(res)

                res = next(map_rotation)
                if res:
                    self.pipe_end.send(res)

                for check in anti_detection:
                    res = next(check)
                    if res:
                        self.pipe_end.send(res)

                res = next(map_rotation)  # Check rotation twice per loop
                if res:
                    self.pipe_end.send(res)

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
