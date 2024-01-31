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
    Whenever that happens, the information should instead be store in the EngineData
    instance that is shared among all generators.
    """

    generator_type: Literal["Rotation", "AntiDetection", "Maintenance"]
    # Specifies which generators are blocked by which other generators
    generators_blockers: dict[int, set[int]] = {}

    def __init__(self, data) -> None:
        self.data = data
        self._error_counter = 0  # For error-handling
        self._blocked_at = self._blocked = None

        self.__class__.generators_blockers[
            id(self)
        ] = set()  # Create a new set for the generator being created

    @property
    def blocked(self) -> bool:
        """
        :return: True if the generator is blocked by any generator, including self.
        False otherwise.
        """
        return len(self.generators_blockers[id(self)]) > 0

    @blocked.setter
    def blocked(self, value: bool) -> None:
        """
        Used by generators to block/unblock themselves.
        If True, adds the generator's id to its own set of blockers.
        If False, removes the generator's id from its own set of blockers.
        """
        if value:
            if not self.blocked:
                logger.debug(f"{self} has blocked itself.")

            DecisionGenerator.generators_blockers[id(self)].add(id(self))
            self.blocked_at = time.perf_counter()
        else:
            was_blocked = self.blocked
            DecisionGenerator.generators_blockers[id(self)].discard(id(self))
            if was_blocked and not self.blocked:
                logger.debug(f"{self} has unblocked itself.")
            self.blocked_at = None

    @property
    def blocked_at(self) -> float | None:
        """
        :return: The time at which the generator was blocked. None if not blocked.
        """
        return self._blocked_at

    @blocked_at.setter
    def blocked_at(self, value: float | None) -> None:
        """
        Used by generators to set the time at which they were blocked.
        If value is None, it means the generator is being unblocked.
        Generators can block themselves or be blocked by others.
        When a new blocked_at value is given, we first check if the generator is newly
        blocked, or if it was already blocked. In the latter case, we do not update the
        blocked_at value.
        The opposite is true when unblocking: we only remove the blocked_at value if
        the generator is being truly unblocked, meaning its own blocker set is now empty
        :return:
        """
        if value is not None:
            # Only assign a value if one doesn't exist already and we are blocked
            if self.blocked and self._blocked_at is None:
                self._blocked_at = value
        else:
            # Only remove the value if we are not blocked
            if not self.blocked:
                self._blocked_at = None

    @staticmethod
    def block_generators(generator_type: str, by_whom: int) -> None:
        """
        Used by generators to block OTHER generators.
        Those are defined as static method because they are often used as callbacks sent
        through a multiprocessing.Pipe back-and-forth. It is much more efficient to use
        static methods in such cases.
        If by_whom = 0, the request was made through discord by the user.
        In such case, all generators of the generator_type are blocked.
        """
        assert generator_type in [
            "Rotation",
            "AntiDetection",
            "Maintenance",
            "All",
        ], f"Invalid generator_type: {generator_type}"
        if by_whom == 0:
            for idx in DecisionGenerator.generators_blockers:
                DecisionGenerator.generators_blockers[idx].add(0)
            return

        self = get_object_by_id(by_whom)
        for idx in DecisionGenerator.generators_blockers:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            condition1 = gen_type == generator_type and generator is not self
            condition2 = generator_type == "All"
            if condition1 or condition2:
                if not getattr(generator, "blocked"):
                    logger.debug(f"{generator} has been blocked by {self}")
                DecisionGenerator.generators_blockers[idx].add(by_whom)
                setattr(generator, "blocked_at", time.perf_counter())

    @staticmethod
    def unblock_generators(generator_type: str, by_whom: int) -> None:
        """
        Used by generators to unblock OTHER generators.
        Those are defined as static method because they are often used as callbacks sent
        through a multiprocessing.Pipe back-and-forth. It is much more efficient to use
        static methods in such cases.
        If by_whom = 0, the request was made through discord by the user.
        In such case, all generators of the generator_type are blocked.
        """
        assert generator_type in [
            "Rotation",
            "AntiDetection",
            "Maintenance",
            "All",
        ], f"Invalid generator_type: {generator_type}"
        if by_whom == 0:
            for idx in DecisionGenerator.generators_blockers:
                DecisionGenerator.generators_blockers[idx].clear()
            return

        self = get_object_by_id(by_whom)
        for idx in DecisionGenerator.generators_blockers:
            generator = get_object_by_id(idx)
            gen_type = getattr(generator, "generator_type")
            condition1 = gen_type == generator_type and generator is not self
            condition2 = generator_type == "All"
            if condition1 or condition2:
                was_blocked = getattr(generator, "blocked")
                DecisionGenerator.generators_blockers[idx].discard(by_whom)
                if was_blocked and not getattr(generator, "blocked"):
                    logger.debug(f"{generator} has been unblocked by {self}")
                setattr(generator, "blocked_at", None)

    def __iter__(self) -> "DecisionGenerator":
        return self

    def __next__(self) -> QueueAction | None:
        """
        Template method for generators.
        If the generator is blocked, see if it was blocked by a user-request from
        Discord, in which case we skip. If it is blocked by other generators, there is a
        hard limit at 300s after which the generator will raise an error.
        This is because we never expect generators to block others for such a long time,
        therefore if that ever happens, it means something is wrong and we should exit.

        If the failsafe is triggered, return the defined failsafe action.
        Otherwise, return the next action from the generator.
        :return:
        """
        if self.blocked:
            if 0 in self.generators_blockers[id(self)]:
                pass
            elif time.perf_counter() - self._blocked_at > 300:
                raise RuntimeError(
                    f"{self} has been blocked for more than 5 minutes. Exiting."
                )
            return

        try:
            self._update_continuous_data()
            failsafe = self._failsafe()
            if failsafe:
                failsafe.process_id = id(self)
                return failsafe

            res = self._next()
        except Exception as e:
            self._error_counter += 1
            handler = self._exception_handler(e)
            if handler:
                handler.process_id = id(self)
                return handler
        else:
            self._error_counter = 0
            if res:
                res.process_id = id(self)
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

        Note: The definition remains vague, so each Generator can implement a vastly
        different logic.
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
        checks. This is called at the beginning of each iteration, provided that the
        generator is unblocked.
        """
        pass

    @abstractmethod
    def _next(self) -> QueueAction | None:
        """
        :return: A QueueAction or None.
        """
        pass
