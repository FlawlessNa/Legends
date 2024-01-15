from abc import ABC, abstractmethod
from .action import QueueAction
from typing import Literal


class DecisionGenerator(ABC):
    generator_type: Literal["Rotation", "AntiDetection", "Maintenance"] = NotImplemented

    def __init__(self, data) -> None:
        self.data = data

    def __iter__(self) -> "DecisionGenerator":
        return self

    def __next__(self):
        blocked = getattr(self.data, repr(self))
        if blocked:
            return

        failsafe = self._failsafe()
        if failsafe:
            return failsafe

        return self._next()

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def _failsafe(self):
        """
        Method used to ensure that a given action has been properly taken.
        :return:
        """
        pass

    @property
    @abstractmethod
    def data_requirements(self) -> tuple[str]:
        """
        :return: A tuple of strings representing the data required by this generator.
        """
        pass

    @abstractmethod
    def _next(self) -> QueueAction | None:
        """
        :return: A QueueAction or None.
        """
        pass
