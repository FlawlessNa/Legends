import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers

from botting.utilities import install_loop_diagnostics, setup_child_proc_logging
from .bot import Bot
from .action_data import ActionRequest

logger = logging.getLogger(__name__)
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
        barrier: multiprocessing.managers.BarrierProxy,
    ) -> None:
        assert multiprocessing.current_process().name != "MainProcess"
        self.pipe = pipe
        self.metadata = metadata
        self.bots = bots
        self.bot_tasks: list[asyncio.Task] = []
        self.main_listener: asyncio.Task | None = None
        self.barrier = barrier

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join([b.ign for b in self.bots])})"

    @classmethod
    def _spawn_engine(
        cls,
        pipe: multiprocessing.connection.Connection,
        metadata: multiprocessing.managers.DictProxy,
        bots: list[Bot],
        barrier: multiprocessing.managers.BarrierProxy,
    ) -> None:
        """
        Child Process Entry Point.
        Creates the Engine instance and starts its DecisionMakers cycles for all
        Monitors.
        :param pipe: a multiprocessing.Connection instance.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :param barrier: a multiprocessing.Barrier instance, used to start all bots at
        the same time.
        :return:
        """
        setup_child_proc_logging(metadata["logging_queue"])
        engine = cls(pipe, metadata, bots, barrier)
        logger.info("%s Started.", engine)
        # None (not False) so that PYTHONASYNCIODEBUG still wins when the flag is off.
        asyncio.run(engine._cycle_forever(), debug=metadata.get("debug") or None)

    async def _cycle_forever(self) -> None:
        """
        Called within Child Process.
        Launches the DecisionMakers of all Bots.
        :return:
        """
        asyncio.current_task().set_name(f"MainTask - {self}")
        install_loop_diagnostics(debug=bool(self.metadata.get("debug")))
        try:
            for bot in self.bots:
                bot.child_init(self.pipe, self.barrier)
                self.bot_tasks.append(
                    asyncio.create_task(bot.start(), name=f"Bot({bot.ign})")
                )
            self.main_listener = asyncio.create_task(
                self._poll_for_updates(), name=f"MainListener - {self}"
            )
            t_done, t_pending = await asyncio.wait(
                [self.main_listener] + self.bot_tasks,
                timeout=_DEBUG_TIMEOUT_,
                return_when=asyncio.FIRST_COMPLETED,
            )
            logger.info("%s has finished waiting due to %s.", self, t_done)

            for task in t_pending:
                logger.info("%s Cancelling task %s", self, task.get_name())
                task.cancel()

            # Several tasks may complete on the same loop iteration, so every member
            # of the done set gets its exception retrieved - inspecting only the first
            # leaves the siblings' failures unretrieved, meaning invisible.
            failures = [
                task
                for task in t_done
                if not task.cancelled() and task.exception() is not None
            ]
            for task in failures:
                logger.error(
                    "%s task %s raised.",
                    self,
                    task.get_name(),
                    exc_info=task.exception(),
                )
            if failures:
                # The whole group is raised, never just .exceptions[0]: a TaskGroup
                # reports every sibling that failed alongside the first one.
                raise failures[0].exception()

        except SystemExit:
            pass

        except Exception as e:
            logger.error("%s is exiting on an exception.", self, exc_info=e)
            raise e

        finally:
            if not self.pipe.closed:
                logger.info("%s is sending None and closing pipe", self)
                self.pipe.send(None)
            logger.info("%s Exited.", self)

    async def _poll_for_updates(self) -> None:
        """
        Parses the pipe for any updates to one BotData instance.
        :return:
        """
        while True:
            if await asyncio.to_thread(self.pipe.poll):
                data = self.pipe.recv()
                if data is None:
                    logger.info("%s received None from MainProcess. Exiting.", self)
                    break
                elif isinstance(data, str):
                    action = data.split()[0].lower()
                    targets = data.split()[1:]
                    for bot in self.bots:
                        if bot.ign in targets or targets == ["All"]:
                            getattr(bot, action)()


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
        barrier: multiprocessing.managers.BarrierProxy,
    ) -> multiprocessing.Process:
        """
        Called from the MainProcess.
        Spawns a new process to handle all Bots associated with this Engine.
        :param pipe: a multiprocessing.Connection instance.
        :param metadata: a multiprocessing.Manager.dict() instance.
        :param bots: a list of Bot instances to include.
        :param barrier: a multiprocessing.Barrier instance, used to start all bots at
        the same time.
        :return:
        """
        assert multiprocessing.current_process().name == "MainProcess"
        process = multiprocessing.Process(
            target=cls._spawn_engine,
            name=f"Engine({', '.join([b.ign for b in bots])})",
            args=(pipe, metadata, bots, barrier),
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
                            logger.error("Exception occurred in %s.", engine.name)

                            discord_pipe.send(
                                f"Exception {request} \n occurred in {engine.name}."
                            )
                            # raise request
                        elif isinstance(request, str):
                            logger.info("Received %s from %s.", request, engine.name)
                            discord_pipe.send(request)

                        await queue.put(request)

            except asyncio.CancelledError:
                logger.info("Listener to %s cancelled.", engine.name)

            except Exception as e:
                logger.error(
                    "Exception occurred in Listener to %s.", engine.name, exc_info=e
                )
                raise e

            finally:
                if not pipe.closed:
                    logger.info("Sending None from %s listener", engine.name)
                    pipe.send(None)
                queue.put_nowait(None)

        return asyncio.create_task(_coro(), name=f"Listener({engine.name})")
