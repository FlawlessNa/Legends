import time
import random

from functools import partial

from botting.core import DecisionGenerator, QueueAction, controller
from botting.utilities import config_reader
from royals import RoyalsData


class PetFood(DecisionGenerator):
    """
    Generator that triggers a pet food consumption every interval.
    Defaults: 10 minutes (600 seconds)
    """
    def __init__(self,
                 data: RoyalsData,
                 interval: int = 600,
                 keyname: str = 'Pet Food') -> None:
        self.data = data
        self._key = eval(config_reader('keybindings', self.data.ign, 'Non Skill Keys'))[keyname]
        self._interval = interval

    def __call__(self):
        self._next_call = 0
        return iter(self)

    def __next__(self) -> QueueAction | None:
        if time.perf_counter() >= self._next_call:
            self._next_call = time.perf_counter() + random.uniform(0.9, 1.1) * self._interval
            action = partial(controller.press,
                             handle=self.data.handle,
                             key=self._key,
                             silenced=True,
                             cooldown=0)
            return QueueAction(self.__class__.__name__, 5, action)

    def _failsafe(self):
        """
        Nothing needed here.
        """
        pass


MountFood = partial(PetFood, keyname='Mount Food')  # Alias, same mechanism
