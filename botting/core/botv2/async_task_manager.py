import asyncio
import logging
from .action_data import ActionRequest

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET

MAX_CONCURRENT_TASKS = 30


class AsyncTaskManager:
    """
    Main Process class for managing asynchronous tasks.
    Task priority, scheduling, and cancellations are handled here.
    """
    _event_loop_overflow = MAX_CONCURRENT_TASKS

    def __init__(self) -> None:
        self.queue = asyncio.Queue()
        self.running_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        while True:
            action_request: ActionRequest = await self.queue.get()
            asyncio.create_task(self._run_task(action_request))

    async def _schedule_task(self, action_request: ActionRequest) -> None:
        task = asyncio.create_task(self)

    def _check_for_event_loop_overflow(self):
        """
        Check if the event loop has too many tasks.
        This method is only called occasionally for debugging purposes.
        """
        if len(self.running_tasks) > self._event_loop_overflow:
            for t in self.running_tasks:
                print(t)
            logger.warning(
                f"Nbr of tasks scheduled from ActionRequests in the event loop is "
                f"{len(self.running_tasks)}."
            )
