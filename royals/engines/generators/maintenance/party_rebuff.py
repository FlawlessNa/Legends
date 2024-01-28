import asyncio
import math
import multiprocessing as mp
import random
import time

from botting.core import QueueAction, GeneratorUpdate
from royals.actions import cast_skill
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData, MinimapData
from royals.models_implementations.mechanics import RoyalsSkill


class SkipIteration(Exception):
    pass


class PartyRebuff(IntervalBasedGenerator):
    """
    Generator for rebuffing at a target location, in a multi-client (aka multiprocess)
    context. When a buff is ready to be cast, an Event is triggered, which notifies
    all other Engines, provided they have a PartyRebuff generator as well.
    Once the Event is triggered, all Engines have the same "next_target" such that
    characters join somewhere in the minimap. When ready, the PartyRebuff generator for
    a given Engine waits on a Barrier, and when all are waiting, the barrier is broken
    and all characters cast their buffs.
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign}, {self.buffs})"

    def __init__(
        self,
        data: MaintenanceData | MinimapData,
        notifier: mp.Event,
        barrier: mp.Barrier,
        buffs: list[RoyalsSkill],
        target: tuple[int, int],
        deviation: float = 0.1,
    ):
        assert all(
            skill.cooldown == 0 for skill in buffs
        ), f"Cooldowns should not be included in {self}"
        assert all(
            skill.duration > 0 for skill in buffs
        ), f"One of the skills has no duration."

        interval = min(skill.duration for skill in buffs)
        super().__init__(data, interval, deviation)
        self.notifier = notifier
        self.barrier = barrier
        self.buffs = buffs
        self.target = target

        self._minimap_range = min(
            skill.horizontal_minimap_distance
            for skill in self.buffs
            if skill.horizontal_minimap_distance is not None
        )

    def __next__(self) -> QueueAction | None:
        """
        Each individual Rebuff generator is time-based, but if any of them is triggered,
        then it means it is time to rebuff. In such a case, notify all other Engines
        that have a Rebuff generators through the notifier and force them to execute.
        :return:
        """
        if self.notifier.is_set():
            self._next_call = time.perf_counter()
        return super().__next__()

    def initial_data_requirements(self) -> tuple:
        return tuple()

    def _update_continuous_data(self) -> None:
        """
        Once the generator is called, it means it is time to rebuff. In such a case,
        notify all other Engines that have a Rebuff generators through the notifier.
        :return:
        """
        self.data.update("current_minimap_position")
        self.data.update(next_target=self.target)
        self.notifier.set()

    def _next(self) -> QueueAction | None:
        if (
            math.dist(self.data.current_minimap_position, self.target)
            > self._minimap_range
        ):
            # The Rotation generator will take care of moving to the target
            return
        else:
            # Generator is now ready for rebuff, a barrier blocks it until all others
            # are ready as well. This call is blocking; the entire process is on hold
            # Maximum wait time is 5 seconds
            if self.barrier.wait(timeout=5):  # Returns true only when barrier passes
                return self._rebuff()
            else:
                # Occurs if timeout is reached
                return

    def _failsafe(self):
        # Check if re-buff was successful, in which case the notifier is cleared and
        # next_call is updated.
        # Otherwise, set it once more.
        if ...:  # Successful rebuff
            self.notifier.clear()
            self._next_call = time.perf_counter() + self.interval * (
                random.uniform(1 - self._deviation, 1 - self._deviation / 2)
            )
            self.unblock_generators("Rotation", id(self))
            raise SkipIteration  # skip call to _next()
        else:
            # Re-trigger the notifier for every generators
            self.notifier.set()
            self._next_call = time.perf_counter()
        # Unblock rotation generator

    def _exception_handler(self, e: Exception) -> None:
        if isinstance(e, SkipIteration):
            # Occurs when failsafe is successful
            return

        raise e

    def _rebuff(self) -> QueueAction:
        self.block_generators("Rotation", id(self))
        self.blocked = True
        return QueueAction(
            identifier=f"{self}",
            priority=1,
            action=...,
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={"blocked": False},
            ),
        )

    @staticmethod
    async def _run_all_actions(partials, timeout: int = 5):
        async def _coro():
            await asyncio.sleep(0.25)
            for action in partials:
                await action()

        await asyncio.wait_for(_coro(), timeout=timeout)

    @staticmethod
    async def cast_all(wait_time: float, skills: list[RoyalsSkill], *args):
        await asyncio.sleep(wait_time)
        for skill in skills:
            await cast_skill(*args, skill=skill)
