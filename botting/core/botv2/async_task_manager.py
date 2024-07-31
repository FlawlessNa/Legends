import asyncio
import logging
from dataclasses import dataclass

from .action_data import ActionRequest

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.INFO

MAX_CONCURRENT_TASKS = 30


class AsyncTaskManager:
    """
    Main Process class for managing asynchronous tasks.
    Task priority, scheduling, and cancellations are handled here.
    """
    _event_loop_overflow = MAX_CONCURRENT_TASKS

    def __init__(self) -> None:
        self.queue = asyncio.Queue()
        self.running_tasks: dict[str, ActionRequest] = {}

    async def start(self) -> None:
        while True:
            action_request: ActionRequest = await self.queue.get()
            if action_request is None:
                logger.info("Received None from the queue. Exiting Task Manager.")
                break

            logger.log(LOG_LEVEL, f"Received {action_request}.")
            await self._process_request(action_request)
            self._check_for_event_loop_overflow()

    async def _process_request(self, request: ActionRequest) -> None:
        if request.identifier in self.running_tasks:
            self._handle_duplicate_request(request)
        self._handle_priority(request)

    def _handle_duplicate_request(self, request: ActionRequest) -> None:
        former = self.running_tasks[request.identifier]
        if request.cancels_itself:
            former.task.cancel()
            self.running_tasks.pop(request.identifier)
        else:
            raise ValueError(
                f"Task {request.identifier} already exists and can't cancel itself"
            )

    def _handle_priority(self, request: ActionRequest) -> None:
        if request.priority > self._get_priority_blocking():
            self._schedule_task(request)
        elif request.requeue_if_not_scheduled:
            self.queue.put_nowait(request)

    def _get_priority_blocking(self) -> int:
        """
        :return:
        """
        return max(
            (
                r.priority for r in self.running_tasks.values()
                if r.block_lower_priority
            ),
            default=0
        )

    def _schedule_task(self, request: ActionRequest) -> None:
        request.task = asyncio.create_task(request.procedure(), name=request.identifier)
        request.task.add_done_callback(self._cleanup_handler)
        if request.callback:
            request.task.add_done_callback(self.cb_wrapper(request.callback))
        self.running_tasks[request.identifier] = request

    def _cleanup_handler(self, fut):
        # TODO - Handling of future result back to the DecisionMaker
        try:
            exception = fut.exception()
            if exception:
                logger.error(f"Exception occurred in task {fut.get_name()}: {exception}")
                raise exception
        except (asyncio.CancelledError, TimeoutError):
            pass
        except Exception:
            raise
        finally:
            self.running_tasks.pop(fut.get_name())

    def _check_for_event_loop_overflow(self):
        """
        Check if the event loop has too many tasks.
        This method is only called occasionally for debugging purposes.
        """
        if len(self.running_tasks) > self._event_loop_overflow:
            logger.warning(
                f"Nbr of tasks scheduled from ActionRequests in the event loop is "
                f"{len(self.running_tasks)}."
            )

    @staticmethod
    def cb_wrapper(func) -> callable:
        """
        Wraps a function to be called as a callback, ignoring the Future object
        automatically passed by task.add_done_callback.
        :param func: a function.
        :return: a function.
        """
        def _wrapper(fut):
            return func()
        return _wrapper
