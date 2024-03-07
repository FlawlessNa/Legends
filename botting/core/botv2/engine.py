import multiprocessing.connection
import multiprocessing.managers

from botting.utilities import setup_child_proc_logging
from .bot import Bot


class Engine:
    """
    Lives in a ChildProcess.
    An engine instance is a container of Bot instances.
    It cycles through each Bot instance, calling their DecisionMakers one at a time.
    It is responsible for passing on the ActionData instances returned by the
    DecisionMakers to the Main Process, as well as receiving (from Main Process)
    residual BotData attributes to update.
    """

    def __init__(
        self,
        pipe: multiprocessing.connection.Connection,
        metadata: multiprocessing.managers.DictProxy,
        bots: list[Bot],
    ) -> None:
        assert multiprocessing.current_process().name != "MainProcess"
        self.pipe = pipe
        self.metadata = metadata
        self.bots = bots

    @classmethod
    def start(
        cls,
        pipe: multiprocessing.connection.Connection,
        metadata: multiprocessing.managers.DictProxy,
        bots: list[Bot],
    ) -> multiprocessing.Process:
        """
        Called from the MainProcess.
        Spawns a new process to handle all Bots associated with this Engine.
        :param pipe: a multiprocessing.Connection instance.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :return:
        """
        assert multiprocessing.current_process().name == "MainProcess"
        process = multiprocessing.Process(
            target=cls._spawn_engine,
            # name=f"Engine[{', '.join([b.name for b in bots])}]",
            args=(pipe, metadata, bots),
        )
        process.start()
        return process

    @classmethod
    def _spawn_engine(
        cls,
        pipe: multiprocessing.connection.Connection,
        metadata: multiprocessing.managers.DictProxy,
        bots: list[Bot],
    ) -> None:
        """
        Child Process Entry Point.
        Creates the Engine instance and starts its DecisionMakers cycles for all
        Monitors.
        :param pipe: a multiprocessing.Connection instance.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :return:
        """
        setup_child_proc_logging(metadata["Logging Queue"])
        engine = cls(pipe, metadata, bots)
        engine._cycle_forever()

    def _cycle_forever(self) -> None:
        """
        Called within Child Process.
        Cycles through all Bots, calling their DecisionMakers one at a time.
        :return:
        """
        while True:
            self._poll_for_updates()

            for bot in self.bots:
                self._iterate_once(bot)

    def _poll_for_updates(self) -> None:
        """
        Parses the pipe for any updates to one BotData instance.
        :return:
        """
        while self.pipe.poll():
            data_updater = self.pipe.recv()
            self.bots[data_updater.id].update(data_updater)
            
    def _iterate_once(self, bot: Bot) -> None:
        """
        Calls the DecisionMakers of a single Bot instance.
        :param bot:
        :return:
        """
        for decision_maker in bot.decision_makers:
            action_data = decision_maker()
            if action_data is not None:
                self.pipe.send(action_data)

    # def _exit(self) -> None:
    #     """
    #     This method is called when the Engine is about to be terminated.
    #     Performs any necessary clean-up.
    #     1. Ensures not keys are being held down on any of the bots.
    #     2.
    #     :return:
    #     """
    #     for monitor in self.monitors:
    #         for key in ["up", "down", "left", "right"]:
    #             asyncio.run(
    #                 controller.press(
    #                     bot.handle, key, silenced=False, down_or_up="keyup"
    #                 )
    #             )
