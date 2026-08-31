import asyncio
import logging
import multiprocessing.connection

from ..telemetry import emit_event
from ..telemetry_events import (
    ACTION_BLOCKED,
    ACTION_CANCELS_OTHER,
    ACTION_REQUEUED,
    ACTION_SCHEDULED,
    ACTION_SELF_CANCELLED,
    ActionCancelsOtherPayload,
    ActionPayload,
)
from .action_data import ActionRequest

logger = logging.getLogger(__name__)

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
            elif isinstance(action_request, BaseException):
                logger.error(
                    "Received an exception from the queue. Exiting Task Manager.",
                    exc_info=action_request,
                )
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
            self._emit(ACTION_SELF_CANCELLED, request)
            former.task.cancel()
        else:
            raise ValueError(
                f"Task {request.identifier} already exists and can't cancel itself"
            )

    def _emit(self, event_type: str, request: ActionRequest) -> None:
        """
        Emit one ``action.*`` Telemetry Record for a request Main Process is
        disposing of.

        Unconditional, unlike the text logs these records replace. Those were
        gated on a per-request ``log`` flag - severity and visibility conflated
        at the call site, which is the conflation ADR-0001 exists to undo. The
        Correlation ID rides on the request, so this is where a decision made in
        an Engine is joined to what Main Process did with it.

        :param event_type: One of the ``ACTION_*`` constants.
        :param request: The request being disposed of.
        """
        payload: ActionPayload = {
            "identifier": request.identifier,
            "priority": int(request.priority),
        }
        emit_event(
            request.correlation_id, event_type, payload, logger_name=logger.name
        )

    async def _handle_priority(self, request: ActionRequest) -> None:
        if request.priority >= self._get_priority_blocking():
            self._emit(ACTION_SCHEDULED, request)
            await self._schedule_task(request)
        elif request.requeue_if_not_scheduled:
            self._emit(ACTION_REQUEUED, request)
            # Self-inflicted delay to avoid infinite re-queueing
            asyncio.get_running_loop().call_later(1.0, self.queue.put_nowait, request)
            # await self.queue.put(request)
        else:
            self._emit(ACTION_BLOCKED, request)
            if request.callbacks:
                for cb in request.callbacks:
                    cb()

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
                cancels: ActionCancelsOtherPayload = {
                    "identifier": request.identifier,
                    "cancelled": task,
                }
                emit_event(
                    request.correlation_id,
                    ACTION_CANCELS_OTHER,
                    cancels,
                    logger_name=logger.name,
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
        self.running_tasks[request.identifier] = request

    def _cleanup_handler(self, fut):
        # TODO - Handling of future result ba        ck to the DecisionMaker
        try:
            exception = fut.exception()
            if exception:
                logger.error(
                    "Exception occurred in task %s: %s",
                    fut.get_name(),
                    exception,
                    exc_info=exception,
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
                "Nbr of tasks scheduled from ActionRequests in the event loop is %s.",
                len(self.running_tasks),
            )

    def _check_for_queue_overflow(self):
        """
        Check if the queue has too many tasks.
        This method is only called occasionally for debugging purposes.
        """
        if self.queue.qsize() > self._event_loop_overflow:
            logger.warning(
                "Nbr of tasks scheduled from ActionRequests in the queue is %s.",
                self.queue.qsize(),
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
