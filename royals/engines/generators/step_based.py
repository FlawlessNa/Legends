import logging

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
        self._current_step = self._current_step_executed = 0
        self._failsafe_enabled = True

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
        if value > self.num_steps + 1:
            raise ValueError(f"{self} has incremented current_step too much.")
        else:
            self._current_step = value

    def _next(self) -> QueueAction | None:
        res = None
        if self.current_step < self.num_steps:
            res = self.steps[self.current_step]()
            self._current_step_executed += 1
            if self._current_step_executed >= 30:
                raise ValueError(f"{self} has executed the same step too many times.")

        if res is None:
            self.current_step += 1
            self._failsafe_enabled = True
            self._current_step_executed = 0
        return res
