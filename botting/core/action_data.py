import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ActionRequest:
    """
    A data container sent by any DecisionMaker to the Main process.
    May contain the following:
    - Action to be performed, if any
    - BotData attributes to be updated after the action is performed, if any
    - Request to block/unblock any other DecisionMaker(s) from any Bot/Engine.
    - Any Message to be sent to the user through the Peripheral Process.
    - Any task priority and scheduling attribute, used by Main Process to handle
    task management.
    """

    identifier: str
    # `Any` rather than a coroutine type, deliberately. Main Process does
    # `asyncio.create_task(procedure(...))`, so the de-facto contract *is* a
    # coroutine function - but `BaseParser._kill` is a plain `def`, so declaring
    # that would turn a latent defect into a type error at a call site this
    # dataclass cannot fix. Issue #130 owns the real answer, which changes how
    # the Discord KILL command behaves and needs a running Session to settle.
    procedure: Callable[..., Any]
    ign: str
    priority: int = field(default=1)  # Higher priority tasks have more control

    # Whether to cancel a task with same identifier
    cancels_itself: bool = field(default=False)
    cancel_tasks: list[str] = field(default_factory=list)

    # Used when this task is blocked from being scheduled by another task
    requeue_if_not_scheduled: bool = field(default=True)

    # Used to block lower priority tasks from being scheduled
    block_lower_priority: bool = field(default=False)

    callbacks: list[Callable[[], object]] = field(default_factory=list)

    # Called in Main Process with the procedure's return value, once its task
    # completes successfully. Not called when the request is blocked, cancelled,
    # or raises - a preempted send loop reports nothing, by design (its Delivered
    # Prefix is the Held-Keys Ledger's business, not the caller's). This is the
    # narrow slice of "handling of future result back to the DecisionMaker" that
    # movement recovery's Delivery Gate needs; each callable must be picklable,
    # e.g. a partial over a manager proxy.
    result_callbacks: list[Callable[[object], object]] = field(default_factory=list)
    task: asyncio.Task | None = field(default=None, init=False)
    discord_request: DiscordRequest | None = field(default=None)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    # Identifies the DecisionMaker._decide() call this request originated from.
    # Stamped at send time by DecisionMaker.send(); None when no decision caused it.
    correlation_id: str | None = field(default=None)

    def __lt__(self, other: ActionRequest | None) -> bool:
        """
        Used by the PriorityQueue to determine the order of tasks.
        :param other:
        :return:
        """
        if other is None:
            return False
        return self.priority > other.priority

    def __gt__(self, other: ActionRequest | None) -> bool:
        """
        Used by the PriorityQueue to determine the order of tasks.
        :param other:
        :return:
        """
        if other is None:
            return True
        return self.priority < other.priority


@dataclass
class DiscordRequest:
    msg: str
    img: np.ndarray | None = field(default=None)


class ActionWithValidation:
    def __init__(
        self,
        pipe: multiprocessing.connection.Connection,
        validator: Callable[[], bool],
        condition: threading.Condition,
        timeout: float,
        max_trials: int = 10,
        correlation_id: str | None = None,
    ) -> None:
        self.pipe = pipe
        self.validator = validator
        self.condition = condition
        self.timeout = timeout
        self.max_trials = max_trials
        self.correlation_id = correlation_id

        self.trials = 0

    def execute_blocking(self, action: ActionRequest) -> None:
        """
        This must be called from within an Engine process.
        Blocks the entire Engine process until the action is validated, allowing
        the procedure to be executed uninterrupted by other tasks.
        # TODO - see if it makes more sense to  use wait_for and to continuously fire
        # the procedure. Once the predicate is met, another request with same identifier
        # is sent to the Engine to cancel itself and stop procedure.
        :return:
        """
        action.procedure = self._wrap(action.procedure)
        now = time.perf_counter()

        while not self.validator():
            self._send_and_wait(action, now)
            self._check_for_trials(action)

    async def execute_async(self, action: ActionRequest) -> None:
        """
        This must be called from within an Engine process.
        Does not block the Engine process, but instead schedules the action to be
        executed asynchronously.
        :param action:
        :return:
        """
        action.procedure = self._wrap(action.procedure)
        now = time.perf_counter()

        while not self.validator():
            await asyncio.to_thread(self._send_and_wait, action, now)
            self._check_for_trials(action)

    def _send_and_wait(self, action: ActionRequest, started_at: float) -> None:
        with self.condition:
            # Re-stamped on every attempt: the retry loop re-sends the same object.
            action.correlation_id = self.correlation_id
            self.pipe.send(action)
            logger.info(
                "Sent %s to Main Process with the condition ID: %s",
                action.identifier,
                id(self.condition),
            )
            if time.perf_counter() - started_at > self.timeout:
                raise TimeoutError(f"{action.identifier} failed validation")
            elif not self.condition.wait(timeout=self.timeout):
                logger.info(
                    "Attempted to wait for condition ID %s but timed out after %s "
                    "seconds.",
                    id(self.condition),
                    self.timeout,
                )
                raise TimeoutError(f"{action.identifier} failed validation")

    def _check_for_trials(self, action: ActionRequest) -> None:
        self.trials += 1
        if self.trials >= self.max_trials:
            raise TimeoutError(
                f"{action.identifier} failed validation after {self.max_trials} trials."
            )

    def _wrap(
        self, procedure: Callable[..., Awaitable[object]]
    ) -> Callable[..., Awaitable[None]]:
        """
        Wraps the procedure within the ActionRequest such that it acquires the Condition
        object and releases it once the procedure completes.
        :param procedure:
        :return:
        """
        return partial(self._wrapped_procedure, procedure, self.condition, self.timeout)

    @staticmethod
    async def _wrapped_procedure(
        procedure: Callable[..., Awaitable[object]],
        condition: threading.Condition,
        timeout: float,
        *args: object,
        **kwargs: object,
    ) -> None:
        _conditional_proc = ActionWithValidation._conditional_procedure(
            procedure, condition, *args, **kwargs
        )
        try:
            await asyncio.wait_for(_conditional_proc, timeout=timeout)
        except TimeoutError:
            raise TimeoutError(
                f"Procedure {procedure} timed out after {timeout} seconds."
            )

    @staticmethod
    async def _conditional_procedure(
        procedure: Callable[..., Awaitable[object]],
        condition: threading.Condition,
        *args: object,
        **kwargs: object,
    ) -> object:
        while True:
            logger.info("Attempting to acquire condition ID %s", id(condition))
            if not condition.acquire(timeout=0.1):
                await asyncio.sleep(0.1)
            else:
                logger.info("Acquired condition ID %s", id(condition))
                try:
                    res = await procedure(*args, **kwargs)
                    condition.notify_all()
                    break
                finally:
                    condition.release()
                    logger.info("Released condition ID %s", id(condition))
        return res
