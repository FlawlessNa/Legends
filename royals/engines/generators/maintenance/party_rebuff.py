import asyncio
import math
import multiprocessing as mp
from royals.engines.generators.base_rotation import RotationGenerator


class LocalizedRebuff(RotationGenerator):
    """
    Generator for rebuffing at a target location.
    All party buffs are cast when at location.
    """

    def __init__(
        self,
        data: RotationData,
        lock: mp.Lock,
        teleport_skill: Skill,
        buffs: list[Skill],
        target: tuple[int, int],
        cooldown: int = 5,
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
        self.data.update("current_minimap_position")
        return iter(self)

    def __next__(self) -> QueueAction | None:
        if time.perf_counter() >= self._next_call:
            if (
                math.dist(self.data.current_minimap_position, self.target)
                > self._minimap_range
            ):
                self.data.update(next_target=self.target)
            else:
                self._next_call = time.perf_counter() + (
                    min(skill.duration for skill in self.buffs) * random.uniform(0.9, 1)
                )
                wait_time = max(
                    self.data.ultimate.animation_time
                    - (time.perf_counter() - self.data.last_cast),
                    0,
                )
                action = partial(
                    self.cast_all,
                    wait_time,
                    self.buffs,
                    self.data.handle,
                    self.data.ign,
                )
                return QueueAction(
                    "Rebuffing on Party", 2, action, is_cancellable=False
                )

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
    async def cast_all(wait_time: float, skills: list[Skill], *args):
        await asyncio.sleep(wait_time)
        for skill in skills:
            await cast_skill(*args, skill=skill)

    def _rotation(self):
        pass

    def _set_next_target(self):
        pass
