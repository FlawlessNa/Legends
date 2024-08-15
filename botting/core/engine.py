import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers

from botting.utilities import setup_child_proc_logging
from .bot import Bot
from .action_data import ActionRequest

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET
_DEBUG_TIMEOUT_ = None  # None to run infinitely. Otherwise, this stops the engine


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
        self.bot_tasks: list[asyncio.Task] = []
        self.main_listener: asyncio.Task | None = None

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
        setup_child_proc_logging(metadata["logging_queue"])
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
            self.main_listener = asyncio.create_task(
                self._poll_for_updates(), name=f"{self} MainListener"
            )
            t_done, t_pending = await asyncio.wait(
                [self.main_listener] + self.bot_tasks,
                timeout=_DEBUG_TIMEOUT_,
                return_when=asyncio.FIRST_COMPLETED,
            )
            logger.info(f"{self} has finished waiting due to {t_done}.")

            for task in t_pending:
                logger.info(f"{self} Cancelling task {task.get_name()}")
                task.cancel()
            if t_done:
                t_done = t_done.pop()

                if t_done.exception():
                    if isinstance(t_done.exception(), ExceptionGroup):
                        raise t_done.exception().exceptions[0]
                    else:
                        raise t_done.exception()

        except SystemExit:
            pass

        except Exception as e:
            logger.error(f"Exception occurred in {self}: {e}.")
            self.pipe.send(e)
            raise

        finally:
            if not self.pipe.closed:
                logger.info(f"{self} is sending None and closing pipe")
                self.pipe.send(None)
            logger.info(f"{self} Exited.")

    async def _poll_for_updates(self) -> None:
        """
        Parses the pipe for any updates to one BotData instance.
        :return:
        """
        while True:
            if await asyncio.to_thread(self.pipe.poll):
                data = self.pipe.recv()
                if data is None:
                    logger.info(f"{self} received None from MainProcess. Exiting.")
                    break
                else:
                    breakpoint()  # TODO


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
                        request: ActionRequest = pipe.recv()

                        if request is None:
                            msg = f"Received None from {engine.name}. Exiting."
                            logger.info(msg)
                            break

                        elif isinstance(request, BaseException):
                            logger.error(f"Exception occurred in {engine.name}.")

                            discord_pipe.send(
                                f"Exception {request} \n occurred in {engine.name}."
                            )
                            raise request
                        elif isinstance(request, str):
                            logger.info(f"Received {request} from {engine.name}.")
                            discord_pipe.send(request)

                        await queue.put(request)

            except asyncio.CancelledError:
                logger.info(f"Listener to {engine.name} cancelled.")

            except Exception as e:
                logger.error(f"Exception occurred in Listener to {engine.name}.")
                raise e

            finally:
                if not pipe.closed:
                    logger.info(f"Sending None from {engine.name} listener")
                    pipe.send(None)
                queue.put_nowait(None)

        return asyncio.create_task(_coro(), name=f"Listener({engine.name})")
