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
        self, metadata: multiprocessing.managers.DictProxy, bots: list[Bot]
    ) -> None:
        assert multiprocessing.current_process().name != "MainProcess"
        self.metadata = metadata
        self.bots = bots

    @classmethod
    def start(
        cls, metadata: multiprocessing.managers.DictProxy, bots: list[Bot]
    ) -> multiprocessing.Process:
        """
        Called from the MainProcess.
        Spawns a new process to handle all Bots associated with this Engine.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :return:
        """
        assert multiprocessing.current_process().name == "MainProcess"
        process = multiprocessing.Process(
            target=cls._spawn_engine,
            name=f"Engine[{', '.join([b.name for b in bots])}]",
            args=(metadata, bots),
        )
        process.start()
        return process

    @classmethod
    def _spawn_engine(
        cls, metadata: multiprocessing.managers.DictProxy, bots: list[Bot]
    ) -> None:
        """
        Child Process Entry Point.
        Creates the Engine instance and starts its DecisionMakers cycles for all
        Monitors.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :return:
        """
        setup_child_proc_logging(metadata["Logging Queue"])
        engine = cls(metadata, bots)

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
