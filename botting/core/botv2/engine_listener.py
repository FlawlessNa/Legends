import asyncio
import logging
import multiprocessing.connection

from .action_data import ActionData
from .engine import Engine

logger = logging.getLogger(__name__)


class EngineListener:
    """
    Lives in the MainProcess.
    An EngineListener is linked to a single Engine instance through a multiprocessing
    Connection. It receives ActionData containers from the Engine and schedules them
    into tasks. It also sends back residual MonitorData attributes to the Engine.
    """
    def __init__(
        self,
        engine: Engine,
        pipe_to_discord: multiprocessing.connection.Connection
    ) -> None:
        self.engine = engine
        self.discord_pipe = pipe_to_discord
        self.engine_side, self.listener_side = multiprocessing.Pipe()

        self.task = None  # asyncio.Task, strong ref to avoid garbage collection

    def __repr__(self):
        return f"{self.__class__.__name__}({self.engine})"

    async def start(self):
        """
        Starts the EngineListener's main loop.
        Perpetually listens for ActionData containers received through the Pipe from the
        Engine and schedules them into tasks.
        If any process/task sends None through a Pipe, the entire program exits.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.listener_side.poll):
                queue_item: ActionData = self.listener_side.recv()

                if queue_item is None:
                    err_msg = f"{self} received None from {self.engine}. Exiting."
                    logger.error(err_msg)
                    raise SystemExit(err_msg)

                elif isinstance(queue_item, BaseException):
                    logger.error(
                        f"Exception occurred in {self.engine}."
                    )

                    self.discord_pipe.send(
                        f'Exception {queue_item} \n occurred in {self.engine}.'
                    )
                    raise queue_item

                logger.debug(f"{queue_item} received from {self.engine}.")
                new_task = self.create_task(queue_item)
                if new_task is not None:
                    logger.debug(f"Created task {new_task.get_name()}.")
                    if queue_item.disable_lower_priority:
                        Executor.priority_levels.append(queue_item.priority)
                        new_task.add_done_callback(
                            partial(
                                self.clear_priority_level, queue_item.priority
                            )
                        )

                self._task_cleanup()

                if len(asyncio.all_tasks()) > 30:
                    for t in asyncio.all_tasks():
                        print(t)
                    logger.warning(
                        f"Nbr of tasks in the event loop is {len(asyncio.all_tasks())}."
                    )