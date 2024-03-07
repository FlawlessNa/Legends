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
    into tasks. It also sends back residual BotData attributes to the Engine.
    """
    def __init__(
        self,
        pipe: multiprocessing.connection.Connection,
        async_queue: asyncio.Queue
    ) -> None:
        self.pipe = pipe
        self.async_queue = async_queue

        self.task = None  # asyncio.Task, strong ref to avoid garbage collection

    def __repr__(self):
        return f"{self.__class__.__name__}({self.engine})"

    async def start(self):
        """
        Starts the EngineListener's main loop.
        Perpetually listens for ActionData containers received through the Pipe from the
        associated Engine. Relays those into the asyncio.Queue, handled by the
        SessionManager.
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

                # TODO - Add additional data to ActionData, such as self.pipe,
                # Such that the callbacks are sent through the proper pipe.
                self.async_queue.put_nowait(queue_item)
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