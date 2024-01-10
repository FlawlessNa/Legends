import asyncio
import math
import multiprocessing as mp
import random
import time

from functools import partial

from botting.core import DecisionGenerator, QueueAction
from botting.models_abstractions import Skill
from ..rotations.base_rotation import Rotation
from royals import RoyalsData
from royals.actions import cast_skill
from royals.models_implementations.mechanics.path_into_movements import get_to_target


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

    def __next__(self) -> QueueAction | None:
        if time.perf_counter() >= self._next_call:
            self._next_call = time.perf_counter() + (
                max(self._skill.duration, self._skill.cooldown) * random.uniform(0.9, 1)
            )
            action = partial(cast_skill, self.data.handle, self.data.ign, self._skill)
            return QueueAction(self._skill.name, 5, action)

    def _failsafe(self, *args, **kwargs):
        pass


class LocalizedRebuff(Rotation):
    """
    Generator for rebuffing at a target location.
    All party buffs are cast when at location.
    """
    def __init__(
        self,
        data: RoyalsData,
        lock: mp.Lock,
        teleport_skill: Skill,
        buffs: list[Skill],
        target: tuple[int, int],
        cooldown: int = 5
    ):
        super().__init__(data, lock, teleport_skill)
        self.buffs = buffs
        self.target = target
        self._cooldown = cooldown

    def __call__(self) -> iter:
        assert all(
            skill.duration > 0 for skill in self.buffs
        ), f"One of the skills has no duration."
        self._next_call = 0
        self._minimap_range = min(
            skill.horizontal_minimap_distance
            for skill in self.buffs
            if skill.horizontal_minimap_distance is not None
        )
        self._acquired = False
        return iter(self)

    def __next__(self) -> QueueAction | None:
        if time.perf_counter() >= self._next_call:
            if (
                math.dist(self.data.current_minimap_position, self.target)
                > self._minimap_range
            ):
                self.data.update(next_target=self.target)
                # actions = get_to_target(
                #     self.data.current_minimap_position,
                #     self.target,
                #     self.data.current_minimap,
                # )
                # res = self._create_partial(actions[0])
                # self._next_call = time.perf_counter() + res.keywords.get('duration', self._cooldown)
                # if not self._acquired:
                #     self._lock.acquire(block=True)
                # self._acquired = True
                # return QueueAction(
                #     identifier=self.__class__.__name__,
                #     priority=2,
                #     action=res,
                #     is_cancellable=False,
                # )
            else:
                print('Rebuffing')
                self._next_call = time.perf_counter() + (
                    min(skill.duration for skill in self.buffs) * random.uniform(0.9, 1)
                )
                action = partial(self.cast_all, self.buffs, self.data.handle, self.data.ign)
                return QueueAction("Rebuffing on Party", 2, action, is_cancellable=False)

    def _failsafe(self, *args, **kwargs):
        pass

    @staticmethod
    async def _run_all_actions(partials, timeout: int = 5):
        async def _coro():
            await asyncio.sleep(0.25)
            for action in partials:
                await action()
        await asyncio.wait_for(_coro(), timeout=timeout)

    @staticmethod
    async def cast_all(skills: list[Skill], *args):
        for skill in skills:
            await cast_skill(*args, skill=skill)

    def _single_iteration(self):
        pass

    def _set_next_target(self):
        pass
