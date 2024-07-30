import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers

from botting.utilities import setup_child_proc_logging
from .bot import Bot
from .action_data import ActionRequest

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET


class _ChildProcessEngine:
    """
    Engine methods called within a Child (spawned) Process.
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
        self.bot_tasks = []

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join([b.ign for b in self.bots])})"

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
        logger.info(f"{engine} Started.")
        asyncio.run(engine._cycle_forever())

    async def _cycle_forever(self) -> None:
        """
        Called within Child Process.
        Launches the DecisionMakers of all Bots.
        :return:
        """
        try:
            for bot in self.bots:
                bot.child_init(self.pipe)
                self.bot_tasks.append(
                    asyncio.create_task(bot.start(), name=f"Bot({bot.ign})")
                )
            await asyncio.gather(*self.bot_tasks)
            logger.log(LOG_LEVEL, f"{self} gathered all tasks.")

        except SystemExit:
            pass

        except Exception:
            logger.error(f"Exception occurred in {self}.")
            raise

        finally:
            if not self.pipe.closed:
                logger.info(f"{self} is sending None and closing pipe")
                self.pipe.send(None)
            logger.info(f"{self} Exited.")

    # def _poll_for_updates(self) -> None:
    #     """
    #     Parses the pipe for any updates to one BotData instance.
    #     :return:
    #     """
    #     while self.pipe.poll():
    #         data_updater: UpdateRequest = self.pipe.recv()
    #         if data_updater is None:
    #             logger.info(f"{self} received None from MainProcess. Exiting.")
    #             raise SystemExit(f"{self} received None from MainProcess. Exiting")
    #
    #         assert isinstance(data_updater, UpdateRequest), "Invalid signal type"
    #         # TODO - Update BotData

    # def _iterate_once(self, bot: Bot) -> None:
    #     """
    #     Calls the DecisionMakers of a single Bot instance.
    #     :param bot:
    #     :return:
    #     """
    #     for decision_maker in bot.decision_makers:
    #         request: ActionRequest = decision_maker()
    #         if request is not None:
    #             self.pipe.send(request)

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


class Engine(_ChildProcessEngine):
    """
    Lives in a ChildProcess.
    An engine instance is a container of Bot instances.
    It cycles through each Bot instance, calling their DecisionMakers one at a time.
    If any DecisionMaker triggers an ActionRequest instance, it is sent to the
    MainProcess.
    The Engine.listener() method lives within the MainProcess to monitor those
    ActionRequest instances and dispatch to TaskManager.
    """

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
            name=f"Engine({', '.join([b.ign for b in bots])})",
            args=(pipe, metadata, bots),
        )
        process.start()
        return process

    @staticmethod
    def listener(
        pipe: multiprocessing.connection.Connection,
        queue: asyncio.Queue,
        engine: multiprocessing.Process,
        discord_pipe: multiprocessing.connection.Connection,
    ) -> asyncio.Task:
        """
        Called from the MainProcess.
        Creates a new asyncio.Task within MainProcess, responsible to listen to the
        Engine and relay its content to the TaskManager.
        :param pipe: a multiprocessing.Connection instance to the Engine.
        :param queue: an asyncio.Queue instance.
        :param engine: The spawned process connected at the other end of the pipe.
        :param discord_pipe: a multiprocessing.Connection instance to the Peripherals.
        :return:
        """
        assert multiprocessing.current_process().name == "MainProcess"

        async def _coro():
            try:
                while True:
                    if await asyncio.to_thread(pipe.poll):
                        queue_item: ActionRequest = pipe.recv()

                        if queue_item is None:
                            msg = f"Received None from {engine.name}. Exiting."
                            logger.info(msg)
                            break

                        elif isinstance(queue_item, BaseException):
                            logger.error(f"Exception occurred in {engine.name}.")

                            discord_pipe.send(
                                f"Exception {queue_item} \n occurred in {engine.name}."
                            )
                            break

                        # Such that the callbacks are sent through the proper pipe.
                        await queue.put(queue_item)
                        # logger.debug(f"{queue_item} received from {self.engine}.")
                        # new_task = self.create_task(queue_item)
                        # if new_task is not None:
                        #     logger.debug(f"Created task {new_task.get_name()}.")
                        #     if queue_item.disable_lower_priority:
                        #         Executor.priority_levels.append(queue_item.priority)
                        #         new_task.add_done_callback(
                        #             partial(
                        #                 self.clear_priority_level, queue_item.priority
                        #             )
                        #         )
                        #
                        # self._task_cleanup()
                        #
                        # if len(asyncio.all_tasks()) > 30:
                        #     for t in asyncio.all_tasks():
                        #         print(t)
                        #     logger.warning(
                        #         f"Nbr of tasks in the event loop is {len(asyncio.all_tasks())}."
                        #     )
            except asyncio.CancelledError:
                logger.info(f"Listener to {engine.name} cancelled.")

            except Exception:
                logger.error(f"Exception occurred in Listener to {engine.name}.")
                raise

            finally:
                if not pipe.closed:
                    logger.info(f"Sending None from {engine.name} listener")
                    pipe.send(None)
                queue.put_nowait(None)

        return asyncio.create_task(_coro(), name=f"Listener({engine.name})")
