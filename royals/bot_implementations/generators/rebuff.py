import random
import time

from functools import partial

from botting.core import DecisionGenerator, QueueAction
from royals import RoyalsData
from royals.actions import cast_skill
from royals.models_implementations.characters.skills import Skill


class Rebuff(DecisionGenerator):
    """
    Generator for rebuffing.
    """

    def __init__(self, data: RoyalsData, skill: Skill) -> None:
        self.data = data
        self._skill = skill
        self._next_call = None

    def __call__(self) -> iter:
        assert self._skill.duration > 0, f"Skill {self._skill.name} has no duration."
        self._next_call = 0
        return iter(self)

    def __next__(self):
        if time.perf_counter() >= self._next_call:
            self._next_call = time.perf_counter() + (self._skill.duration * random.uniform(0.9, 1))
            action = partial(cast_skill,
                             self.data.handle,
                             self.data.ign,
                             self._skill
                             )
            return QueueAction(self._skill.name,
                               5,
                               action)

    def _failsafe(self):
        pass