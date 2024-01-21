from abc import ABC, abstractmethod
from .pipe_signals import QueueAction
from typing import Literal


class DecisionGenerator(ABC):
    generator_type: Literal["Rotation", "AntiDetection", "Maintenance"]

    def __init__(self, data) -> None:
        self.data = data
        self.blocked = False

        self._error_counter = 0  # For error-handling

    def __iter__(self) -> "DecisionGenerator":
        return self

    def __next__(self) -> QueueAction | None:
        """
        Template method for generators.
        If the generator is blocked, return None and skip.
        If the failsafe is triggered, return the defined failsafe action.
        Otherwise, return the next action from the generator.
        :return:
        """
        if self.blocked:
            return

        try:
            self._update_continuous_data()
            failsafe = self._failsafe()
            if failsafe:
                return failsafe

            res = self._next()
        except Exception as e:
            self._error_counter += 1
            return self._exception_handler(e)
        else:
            self._error_counter = 0
            return res

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def _failsafe(self) -> QueueAction | None:
        """
        Method that should return a QueueAction only if the current generator is failing
        at its task. Generally used to prevent the bot being stuck, or to ensure that
        an action has correctly been completed before moving on.

        Note: The definition remains vague, so each Generator can implement any logic.
        :return:
        """
        pass

    @abstractmethod
    def _exception_handler(self, e: Exception) -> None:
        """
        Method used to handle exceptions raised by the generator.
        Exceptions are not expected, so this method should be used to log the exception
        and potentially try to recover (if possible).
        Otherwise, it should re-raise the exception.
        :param e: Exception raised by the generator.
        :return:
        """
        pass

    @property
    @abstractmethod
    def initial_data_requirements(self) -> tuple:
        """
        :return: A tuple of strings representing the data required to be updated before
        the engine loop starts.
        """
        pass

    @abstractmethod
    def _update_continuous_data(self) -> None:
        """
        Update current Generator attributes and game data attributes before performing
        checks.
        """
        pass

    @abstractmethod
    def _next(self) -> QueueAction | None:
        """
        :return: A QueueAction or None.
        """
        pass
