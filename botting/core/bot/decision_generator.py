import logging
import time
from abc import ABC, abstractmethod
from typing import Literal

from .pipe_signals import QueueAction

logger = logging.getLogger(__name__)


class DecisionGenerator(ABC):
    """
    Base class for all Generators.
    Each generator has its own attribute used to monitor its own status.
    In some cases, multiple generators may need access to the same piece of information.
    Whenever that happens, the information should instead be store in the GameData
    instance that they are using, since GameData is shared among all generators.
    """
    generator_type: Literal["Rotation", "AntiDetection", "Maintenance"]

    def __init__(self, data) -> None:
        self.data = data
        self.data.add_generator_id(id(self))
        self._blocked = False
        self._blocked_at = None
        self._error_counter = 0  # For error-handling

    @property
    def blocked(self) -> bool:
        # return True if self._blocked > 0 else False
        return self._blocked

    @blocked.setter
    def blocked(self, value: bool) -> None:
        # if value and not self.blocked:
        if value and not self._blocked:
            logger.info(f"{self} has been blocked.")
            self._blocked_at = time.perf_counter()
        # elif not value and self._blocked == 1:
        elif not value and self._blocked:
            logger.info(f"{self} has been unblocked.")
            self._blocked_at = None
        # self._blocked += 1 if value else -1
        # self._blocked = max(0, self._blocked)
        self._blocked = value

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
            if time.perf_counter() - self._blocked_at > 300:
                raise RuntimeError(
                    f"{self} has been blocked for more than 5 minutes. Exiting."
                )
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
