import logging
import time

from abc import ABC, abstractmethod

from botting import PARENT_LOG
from botting.core import DecisionGenerator, EngineData, QueueAction


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class StepBasedGenerator(DecisionGenerator, ABC):
    """
    Base class for generators that perform actions that need to be broken down in multi
    steps.
    After the execution of each step, the generator performs calculations and decides
    on the next step to be executed.
    """

    def __init__(
        self,
        data: EngineData,
    ) -> None:
        super().__init__(data)
        self._current_step = 0

    @property
    def num_steps(self) -> int:
        """
        Number of steps to be executed.
        """
        return len(self.steps)

    @property
    @abstractmethod
    def steps(self) -> list[callable]:
        """
        List of steps to be executed.
        """

    @property
    def current_step(self) -> int:
        """
        Current step being executed.
        """
        return self._current_step

    @current_step.setter
    def current_step(self, value: int) -> None:
        """
        Sets the current step being executed. Resets to 0 after all steps have been
        executed.
        """
        if value > self.num_steps:
            self._current_step = 0
        else:
            self._current_step = value

    def __next__(self) -> QueueAction | None:
        """
        # TODO - Currently overwriting DecisionGenerator such that failsafe is called last.
        # TODO - See if that makes sense for all generators, in which case correct DecisionGenerator instead.

        :return:
        """
        if self.blocked:
            if time.perf_counter() - self._blocked_at > 300:
                raise RuntimeError(
                    f"{self} has been blocked for more than 5 minutes. Exiting."
                )
            return

        try:
            self._update_continuous_data()

            res = self.steps[self._current_step]()
            if res:
                res.process_id = id(self)
                self._error_counter = 0
                self.current_step += 1
                return res

            failsafe = self._failsafe()
            if failsafe:
                failsafe.process_id = id(self)
                self._error_counter = 0
                return failsafe

        except Exception as e:
            self._error_counter += 1
            handler = self._exception_handler(e)
            if handler:
                handler.process_id = id(self)
                return handler
