from abc import ABC, abstractmethod
from botting.core import QueueAction
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
        return self._next()

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def _failsafe(self):
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
