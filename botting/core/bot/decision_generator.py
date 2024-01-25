import logging
import time
from abc import ABC, abstractmethod
from typing import Literal

from botting.utilities import get_object_by_id
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
    generators_blockers: dict[int, set[int]] = {}

    def __init__(self, data) -> None:
        self.data = data
        self._error_counter = 0  # For error-handling
        self._blocked_at = self._blocked = None

        self.__class__.generators_blockers[id(self)] = set()

    @property
    def blocked(self) -> bool:
        return len(self.generators_blockers[id(self)]) > 0

    @blocked.setter
    def blocked(self, value: bool) -> None:
        """
         TODO - Used by generators to block themselves. Figure the blocked_at as well.
        """
        if value and not self.blocked:
            logger.info(f"{self} has blocked itself.")
            DecisionGenerator.generators_blockers[id(self)].add(id(self))
            self.blocked_at = time.perf_counter()
        # elif not value and self._blocked == 1:
        elif not value and self.blocked:
            logger.info(f"{self} has unblocked itself.")
            DecisionGenerator.generators_blockers[id(self)].discard(id(self))
            self.blocked_at = None

    @property
    def blocked_at(self) -> float | None:
        return self._blocked_at

    @blocked_at.setter
    def blocked_at(self, value: float | None) -> None:
        if value is None:
            assert self.blocked is False
        elif self.blocked:
            return
        self._blocked_at = value

    @staticmethod
    def block_generators(generator_type: str, by_whom: int) -> None:
        """
        Used by generators to block OTHER generators.
        If by_whom = 0, the request was made through discord by the user.
        In such case, all generators of the generator_type are blocked by all others.
        """
        if by_whom == 0:
            breakpoint()
            return

        self = get_object_by_id(by_whom)
        for idx in DecisionGenerator.generators_blockers:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            condition1 = gen_type == generator_type and generator is not self
            condition2 = generator_type == 'All'
            if condition1 or condition2:
                if not getattr(generator, 'blocked'):
                    logger.info(f'{generator} has been blocked by {self}')
                    setattr(generator, 'blocked_at', time.perf_counter())
                DecisionGenerator.generators_blockers[idx].add(by_whom)

    @staticmethod
    def unblock_generators(generator_type: str, by_whom: int) -> None:
        """
        Used by generators to unblock OTHER generators.
        If by_whom = 0, the request was made through discord by the user.
        In such case, all generators of the generator_type are unblocked by all others.
        """
        if by_whom == 0:
            breakpoint()
            return

        self = get_object_by_id(by_whom)
        for idx in DecisionGenerator.generators_blockers:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            condition1 = gen_type == generator_type and generator is not self
            condition2 = generator_type == 'All'
            if condition1 or condition2:
                was_blocked = getattr(generator, 'blocked')
                DecisionGenerator.generators_blockers[idx].discard(by_whom)
                if was_blocked and not getattr(generator, 'blocked'):
                    logger.info(f'{generator} has been unblocked by {self}')
                    setattr(generator, 'blocked_at', None)

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
