import itertools
import multiprocessing
import time

from abc import ABC, abstractmethod

from .decision_generator import DecisionGenerator
from .executor import Executor
from botting.core.bot.game_data import GameData
from botting.core.bot.pipe_signals import GeneratorUpdate
from botting.utilities import ChildProcess, take_screenshot


class DecisionEngine(ChildProcess, ABC):
    ign_finder: callable  # Returns the handle of a client given its IGN.

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
        Child instances should store in this property the game game_data to share
        across its generators.
        :return: Game game_data.
        """
        pass

    @property
    @abstractmethod
    def items_to_monitor(self) -> list[DecisionGenerator]:
        """
        Child instances should store in this property a list of generators that are
        used for "Maintenance". These are generally uncommon actions that may be
        time-based or trigger-based.
        :return: List of items to monitor.
        """
        pass

    @property
    @abstractmethod
    def next_map_rotation(self) -> DecisionGenerator:
        """
        The generator that dictates map rotation for the current bot.
        :return:
        """
        pass

    @property
    @abstractmethod
    def anti_detection_checks(self) -> list[DecisionGenerator]:
        """
        List of generators that serve as anti-detection mechanisms.
        :return:
        """
        pass

    def _setup_data(self, *generators) -> None:
        """
        This method is called before the main loop starts.
        It is used to update the game data based on the requirements of each generator.
        It also creates a blocking attribute for each generator, along with a status
        attribute.
        :param generators:
        :return:
        """
        for decision_generator in generators:
            self.game_data.update(*decision_generator.initial_data_requirements)

    def start(self) -> None:
        """
        There are three types of generators that are monitored:
        1. Generators that are used to monitor the game state, aka "Maintenance"
        (potions, pet food, inventories, chat feed, proper map, etc.).
        2. Generators that are used to determine the next map rotation.
        3. Generators that are used to prevent detection (anti-detection).

        Before the main loop starts, generators are chained together and game data
        is updated based on the requirements of each generator.
        A blocking attributed is created for each generator, along with a status
        attribute.

        On every iteration,
        - The iteration ID (loop ID) is updated.
        - If the Main Process sent data through the pipe during a callback,
         we retrieve it and update the game data accordingly.
        - All Maintenance generators are checked once.
        - The map rotation generator is checked once.
        - All Anti-Detection generators are checked once.

        If any error occurs and is not handled by a generator, it is sent through
        the pipe and subsequently towards Discord. The program then exits.
        :return: None
        """
        monitors_generators = self.items_to_monitor
        rotation_generator = self.next_map_rotation
        anti_detection_generators = self.anti_detection_checks

        self._setup_data(*itertools.chain(
            monitors_generators, anti_detection_generators, [rotation_generator]
        ))

        try:
            maintenance = [
                iter(gen) for gen in monitors_generators
            ]  # Instantiate all checks generators

            map_rotation = iter(rotation_generator)

            anti_detection = [
                iter(gen) for gen in anti_detection_generators
            ]  # Instantiate all anti-detection checks generators

            while True:
                # Update loop ID and current client image shared across all generators
                self.game_data.current_loop_id = time.perf_counter()

                # Poll the pipe for any updates sent by the main process.
                while self.pipe_end.poll():
                    signal = self.pipe_end.recv()

                    # If main process sends None, it means we are exiting.
                    if signal is None:
                        return

                    # Otherwise, it needs to be a GeneratorUpdate instance
                    assert isinstance(signal, GeneratorUpdate), "Invalid signal type"
                    signal.update_when_done(self.game_data)

                self.game_data.update(current_client_img=take_screenshot(self.handle))
                # Run all generators once
                for gen in itertools.chain(
                    maintenance, anti_detection, [map_rotation]
                ):
                    res = next(gen)
                    if res:
                        self.pipe_end.send(res)

        except Exception as e:
            self.pipe_end.send(e)
            raise

        finally:
            if not self.pipe_end.closed:
                self.pipe_end.send(None)
                self.pipe_end.close()

    @staticmethod
    def start_monitoring(bot: "Executor", log_queue: multiprocessing.Queue, **kwargs):
        """
        This method is called from the Main Process. It starts a child process in which
        the DecisionEngine is instantiated and started.
        :param bot: The Bot instance (living in the main process) to monitor.
        :param log_queue: The logging queue that is used to send logs from the child
         process to the main process.
        :return:
        """
        monitor = bot.engine(log_queue, bot, **kwargs)
        monitor.start()
