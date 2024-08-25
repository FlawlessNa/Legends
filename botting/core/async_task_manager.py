import asyncio
import logging
import multiprocessing.connection

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
    _throttle = 0.1

    def __init__(self, discord_pipe: multiprocessing.connection.Connection) -> None:
        self.queue = asyncio.PriorityQueue()
        self.running_tasks: dict[str, ActionRequest] = {}
        self.discord_pipe = discord_pipe

    async def start(self) -> None:
        while True:
            await asyncio.sleep(self._throttle)
            action_request: ActionRequest = await self.queue.get()
            if action_request is None:
                logger.info("Received None from the queue. Exiting Task Manager.")
                break

            await self._process_request(action_request)
            self._check_for_event_loop_overflow()
            self._check_for_queue_overflow()

    async def _process_request(self, request: ActionRequest) -> None:
        if request.identifier in self.running_tasks:
            self._handle_duplicate_request(request)
        await self._handle_priority(request)

    def _handle_duplicate_request(self, request: ActionRequest) -> None:
        former = self.running_tasks[request.identifier]
        if request.cancels_itself:
            former.task.cancel()
        else:
            raise ValueError(
                f"Task {request.identifier} already exists and can't cancel itself"
            )

    async def _handle_priority(self, request: ActionRequest) -> None:
        if request.priority > self._get_priority_blocking():
            await self._schedule_task(request)
        elif request.requeue_if_not_scheduled:
            logger.log(LOG_LEVEL, f"{request.identifier} has been re-queued.")
            await self.queue.put(request)
        else:
            logger.log(
                logging.INFO,
                f"{request.identifier} has been blocked by higher priority tasks.",
            )

    def _get_priority_blocking(self) -> int:
        """
        :return: The highest priority of all running tasks that prevents lower priorities
        from being scheduled.
        """
        return max(
            (r.priority for r in self.running_tasks.values() if r.block_lower_priority),
            default=0,
        )

    async def _schedule_task(self, request: ActionRequest) -> None:
        for task in request.cancel_tasks:
            if task in self.running_tasks:
                logger.log(
                    LOG_LEVEL, f"{request.identifier} is cancelling task {task}."
                )
                self.running_tasks[task].task.cancel()

        if request.discord_request is not None:
            self.discord_pipe.send(request.discord_request.msg)
            if request.discord_request.img is not None:
                self.discord_pipe.send(request.discord_request.img)

        request.task = asyncio.create_task(
            request.procedure(*request.args, **request.kwargs), name=request.identifier
        )
        request.task.add_done_callback(self._cleanup_handler)
        if request.callbacks:
            for cb in request.callbacks:
                request.task.add_done_callback(self.cb_wrapper(cb))
        if request.cancel_callback is not None:
            request.task.add_done_callback(request.cancel_callback)
        self.running_tasks[request.identifier] = request

    def _cleanup_handler(self, fut):
        # TODO - Handling of future result back to the DecisionMaker
        try:
            exception = fut.exception()
            if exception:
                logger.error(
                    f"Exception occurred in task {fut.get_name()}: {exception}"
                )
                self.queue.put_nowait(None)
                raise exception
        except asyncio.CancelledError:
            pass
        except Exception:
            raise
        finally:
            self.running_tasks.pop(fut.get_name(), None)

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

    def _check_for_queue_overflow(self):
        """
        Check if the queue has too many tasks.
        This method is only called occasionally for debugging purposes.
        """
        if self.queue.qsize() > self._event_loop_overflow:
            logger.warning(
                f"Nbr of tasks scheduled from ActionRequests in the queue is "
                f"{self.queue.qsize()}."
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
