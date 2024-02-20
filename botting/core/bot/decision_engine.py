import itertools
import multiprocessing
import time

from abc import ABC, abstractmethod

from .decision_generator import DecisionGenerator
from .executor import Executor
from botting.core.bot.engine_data import EngineData
from botting.core.bot.pipe_signals import GeneratorUpdate
from botting.utilities import ChildProcess, take_screenshot


class DecisionEngine(ChildProcess, ABC):
    """
    The DecisionEngine is the core of the bot. It is responsible for monitoring the
    status of an individual client and making decisions based on the current game state.
    Each DecisionEngine lives in its own process (aka CPU core).
    This achieves true parallelism for CPU-intensive operations. When decisions are
    made, they are sent to the Main Process through a pipe. The Main Process schedules
    those actions into a single asyncio loop, which is then executed in a single thread.
    In-game actions are therefore executed asynchronously, which is more alike to how
    a human would play the game.
    """

    ign_finder: callable  # Returns the handle of a client given its IGN.

    def __init__(
        self, logging_queue: multiprocessing.Queue, bot: Executor, *args, **kwargs
    ) -> None:
        super().__init__(logging_queue, bot.monitoring_side)
        self.source = repr(bot)
        self.handle = bot.handle
        self.ign = bot.ign

    @property
    @abstractmethod
    def game_data(self) -> EngineData:
        """
        Child instances should store in this property the data to share
        across its generators.
        :return: EngineData child instance.
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
        :param generators:
        :return:
        """
        for decision_generator in generators:
            self.game_data.update(*decision_generator.initial_data_requirements)

    def start(self) -> None:
        """
        There are three types of generators that are monitored:
        1. Generators that are used to monitor the game state, aka "Maintenance"
        (potions, pet food, inventories, etc.).
        2. Generators that are used to determine the next map rotation.
        3. Generators that are used to prevent detection (anti-detection).

        Before the main loop starts, generators are chained together and the game data
        is updated based on the requirements of each generator.

        On every iteration,
        - The iteration ID (loop ID) is updated.
        - If the Main Process sends data through the pipe during a callback (e.g. once
          an action has terminated), the data is retrieved and used to update the
          game data for all generators.
        - Then, all Maintenance generators are checked once.
        - All Anti-Detection generators are checked once.
        - The map rotation generator is checked once.
        - End of loop iteration

        If any error occurs and is not handled by a generator, it is sent through
        the pipe and subsequently towards Discord. The program then exits.
        :return: None
        """
        monitors_generators = self.items_to_monitor
        rotation_generator = self.next_map_rotation
        anti_detection_generators = self.anti_detection_checks

        all_gens = list(
            itertools.chain(
                monitors_generators, anti_detection_generators, [rotation_generator]
            )
        )
        while None in all_gens:
            all_gens.remove(None)

        self._setup_data(*all_gens)

        try:
            maintenance = [
                iter(gen) for gen in monitors_generators
            ]  # Instantiate all checks iterables

            anti_detection = [
                iter(gen) for gen in anti_detection_generators
            ]  # Instantiate all anti-detection checks iterables

            map_rotation = None
            if rotation_generator is not None:
                map_rotation = iter(rotation_generator)

            while True:
                # Update loop ID, data from Main (if any)
                self.game_data.current_loop_id = time.perf_counter()

                # Poll the pipe for any updates sent by the main process.
                while self.pipe_end.poll():
                    signal = self.pipe_end.recv()

                    # If main process sends None, it means we are exiting.
                    if signal is None:
                        return

                    # Otherwise, it needs to be a GeneratorUpdate instance
                    assert isinstance(signal, GeneratorUpdate), "Invalid signal type"

                    if signal.generator_id == 0:
                        # Special case: signal from user received from Discord process.
                        block_status = signal.generator_kwargs.pop("blocked")
                        if block_status:
                            # Automatically blocks all generators
                            DecisionGenerator.block_generators("All", 0)
                        else:
                            # Completely resets all generators
                            DecisionGenerator.unblock_generators("All", 0)
                    else:
                        # Otherwise, signal is a callback from a specific generator.
                        signal.update_when_done(self.game_data)

                # Update client img at every iteration, since used by most generators
                self.game_data.update(current_client_img=take_screenshot(self.handle))

                # Run all generators once. If they return an action, send it to Main.
                if map_rotation is not None:
                    all_iters = itertools.chain(
                        maintenance, anti_detection, [map_rotation]
                    )
                else:
                    all_iters = itertools.chain(maintenance, anti_detection)
                for gen in all_iters:
                    res = next(gen)
                    if res:
                        self.pipe_end.send(res)

        # If any error is un-handled by a generator, send it towards Main and exit.
        except Exception as e:
            self.pipe_end.send(e)
            raise e

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
