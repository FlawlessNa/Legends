import asyncio
import logging

from .task_wrapper import TaskWrapper

logger = logging.getLogger(__name__)


class AsyncTaskManager:
    """
    Main Process class for managing asynchronous tasks.
    Task priority, scheduling, and cancellations are handled here.
    """

    queue = asyncio.Queue()
    client_tasks: list[TaskWrapper] = []
    _event_loop_overflow = 30

    @classmethod
    def _check_for_event_loop_overflow(cls):
        """
        Check if the event loop has too many tasks.
        This method is only called occasionally for debugging purposes.
        """
        _all_tasks = asyncio.all_tasks()
        if len(_all_tasks) > cls._event_loop_overflow:
            for t in _all_tasks:
                print(t)
            logger.warning(f"Nbr of tasks in the event loop is {len(_all_tasks)}.")
