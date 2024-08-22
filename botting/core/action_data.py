import asyncio
import time
import multiprocessing.connection
import multiprocessing.managers
import numpy as np
from dataclasses import field, dataclass
from functools import partial


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
    procedure: callable
    ign: str
    priority: int = field(default=1)  # Higher priority tasks have more control

    # Whether to cancel a task with same identifier
    cancels_itself: bool = field(default=False)
    cancel_tasks: list[str] = field(default_factory=list)

    # Used when this task is blocked from being scheduled by another task
    requeue_if_not_scheduled: bool = field(default=True)

    # Used to block lower priority tasks from being scheduled
    block_lower_priority: bool = field(default=False)

    callbacks: list[callable] = field(default_factory=list)
    task: asyncio.Task = field(default=None, init=False)
    discord_request: "DiscordRequest" = field(default=None)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)


@dataclass
class DiscordRequest:
    msg: str
    img: np.ndarray = field(default=None)


class ActionWithValidation:
    def __init__(
        self,
        pipe: multiprocessing.connection.Connection,
        validator: callable,
        condition: multiprocessing.Condition,
        timeout: float,
        max_trials: int = 10,
    ):
        self.pipe = pipe
        self.validator = validator
        self.condition = condition
        self.timeout = timeout
        self.max_trials = max_trials

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
        if self.validator():
            return

        self._run(action)

    def _run(self, action: ActionRequest) -> None:
        with self.condition:
            now = time.perf_counter()
            while True:
                self.pipe.send(action)
                if time.perf_counter() - now > self.timeout:
                    raise TimeoutError(f"{action.identifier} failed validation.")
                elif not self.condition.wait(timeout=self.timeout):
                    raise TimeoutError(f"{action.identifier} failed validation.")
                if self.validator():
                    break
                self.trials += 1
                if self.trials >= self.max_trials:
                    raise TimeoutError(
                        f"{action.identifier} failed validation after {self.max_trials}"
                        f" trials."
                    )

    async def execute_async(self, action: ActionRequest) -> None:
        """
        This must be called from within an Engine process.
        Does not block the Engine process, but instead schedules the action to be
        executed asynchronously.
        :param action:
        :return:
        """
        action.procedure = self._wrap(action.procedure)
        if self.validator():
            return
        await asyncio.to_thread(self._run, action)

    def _wrap(self, procedure: callable) -> callable:
        """
        Wraps the procedure within the ActionRequest such that it acquires the Condition
        object and releases it once the procedure completes.
        :param procedure:
        :return:
        """
        return partial(self._wrapped_procedure, procedure, self.condition, self.timeout)

    @staticmethod
    async def _wrapped_procedure(
        procedure: callable, condition, timeout: float, *args, **kwargs
    ):
        _conditional_proc = ActionWithValidation._conditional_procedure(
            procedure, condition, *args, **kwargs
        )
        try:
            await asyncio.wait_for(_conditional_proc, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Procedure {procedure} timed out after {timeout} seconds."
            )

    @staticmethod
    async def _conditional_procedure(procedure: callable, condition, *args, **kwargs):
        while True:
            if not condition.acquire(timeout=0.1):
                await asyncio.sleep(0.1)
            else:
                try:
                    res = await procedure(*args, **kwargs)
                    condition.notify()
                    break
                finally:
                    condition.release()
        return res
