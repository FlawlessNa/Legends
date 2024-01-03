from abc import ABC, abstractmethod


class DecisionGenerator(ABC):
    @abstractmethod
    def __call__(self, *args, **kwargs) -> iter:
        pass

    def __iter__(self) -> "DecisionGenerator":
        return self

    def __next__(self):
        pass

    @abstractmethod
    def _failsafe(self):
        pass
