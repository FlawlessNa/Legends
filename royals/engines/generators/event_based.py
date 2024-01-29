import logging
import multiprocessing as mp
import time

from abc import ABC

from botting import PARENT_LOG
from botting.core import DecisionGenerator, EngineData


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class EventBasedGenerator(DecisionGenerator, ABC):
    """
    Base class for generators that perform an action upon an event being triggered.
    """

    def __init__(self, data: EngineData, notifier: mp.Event) -> None:
        super().__init__(data)
        self.notifier = notifier
        self.notifier.set()

    def __next__(self):
        """
        Checks if the multiprocessing notifier is set, in which case the generator is
        triggered.
        :return:
        """
        if not self.notifier.is_set():
            return
        else:
            return super().__next__()
