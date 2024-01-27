import logging
import time

from abc import ABC

from botting import PARENT_LOG
from botting.core import DecisionGenerator, EngineData


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class IntervalBasedGenerator(DecisionGenerator, ABC):
    """
    Base class for generators that perform an action at a given interval.
    """

    def __init__(
        self,
        data: EngineData,
        interval: int,
        deviation: float,
    ) -> None:
        super().__init__(data)
        self.interval = interval
        self._next_call = time.perf_counter()
        self._deviation = deviation

    def __next__(self):
        if time.perf_counter() < self._next_call:
            return
        else:
            return super().__next__()
