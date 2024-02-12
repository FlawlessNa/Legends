import asyncio
import cv2
import logging
import math
import multiprocessing as mp
import os
import random
import time
import win32gui
from functools import partial
from threading import BrokenBarrierError

from botting import PARENT_LOG, ROOT
from botting.core import QueueAction, GeneratorUpdate, DecisionGenerator
from botting.utilities import Box
from royals.actions import cast_skill
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData, MinimapData
from royals.models_implementations.mechanics import RoyalsSkill

logger = logging.getLogger(PARENT_LOG + "." + __name__)

ICONS_PATH = os.path.join(ROOT, f"royals/assets/detection_images")


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

    generator_type = "Maintenance"

    @DecisionGenerator.blocked.setter
    def blocked(self, value) -> None:
        """
        When this generator is unblocked, the ready_counter is incremented
        :return:
        """
        super(PartyRebuff, PartyRebuff).blocked.fset(self, value)
        if value:
            # If self has an actual buff to cast, log the time at which it is cast
            if len(self.buffs) > 0:
                self._blocked_at_logs.append(time.perf_counter())
                while time.perf_counter() - self._blocked_at_logs[0] > 60:
                    self._blocked_at_logs.pop(0)
            if not self.ready_counter.acquire(block=False):
                raise RuntimeError(f"{self} tried to acquire a locked counter.")
        else:
            self.ready_counter.release()

    def __repr__(self) -> str:
        buff_str = ", ".join([buff.name for buff in self.buffs])
        return f"{self.__class__.__name__}({self.data.ign}: {buff_str})"

    def __init__(
        self,
        data: MaintenanceData | MinimapData,
        notifier: mp.Event,  # Notifies it is time to rebuff
        barrier: mp.Barrier,  # Blocks until all bots ready to rebuff
        counter: mp.BoundedSemaphore,  # Used to count how many bots are done rebuffing
        buffs: list[str],
        target: tuple[int, int],
        deviation: float = 0.1,
    ):
        self.buffs = [data.character.skills.get(buff) for buff in buffs]
        while None in self.buffs:
            self.buffs.remove(None)
        if self.buffs:
            interval = min(skill.duration for skill in self.buffs)
            self._minimap_range = min(
                skill.horizontal_minimap_distance
                for skill in self.buffs
                if skill.horizontal_minimap_distance is not None
            )
        else:
            interval = 1000
            self._minimap_range = 5

        super().__init__(data, interval, deviation)

        self.notifier = notifier
        self.barrier = barrier
        self.ready_counter = counter

        self.target = target

        self._full_buff_list = buffs
        self._buff_icons = [
            cv2.imread(os.path.join(ICONS_PATH, f"{buff}.png"))
            for buff in self._full_buff_list
        ]

        self._blocked_at_logs = []

        assert all(
            skill.duration > 0 for skill in self.buffs
        ), f"One of the skills has no duration."
        assert all(
            skill.cooldown == 0 for skill in self.buffs
        ), f"Cooldowns should not be included in {self}"

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

    @property
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
        if (
            not self.notifier.is_set()
            and self.ready_counter.get_value() == self.barrier.parties
        ):
            logger.info(f"{self} has set the rebuff Notifier.")
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
            try:
                logger.info(
                    f"{self} will wait on Barrier with {self.barrier.n_waiting} others."
                )
                self.barrier.wait()  # Returns true only when barrier passes
                return self._rebuff()
            except BrokenBarrierError:
                self.barrier.reset()

    def _failsafe(self):
        """
        Only check for failsafe once all bots have rebuffed, in which case the counter
        will be at max value.
        :return:
        """
        if self.ready_counter.get_value() != self.barrier.parties:
            raise SkipIteration

        elif self._confirm_rebuffed():
            try:
                i = self.barrier.wait()
                if i == 0:
                    logger.info(f"{self} has reset the rebuff Notifier.")
                    self.notifier.clear()

                # If successful, reset for timer + notifier as well as target.
                # self.notifier.clear()
                self._next_call = time.perf_counter() + self.interval * (
                    random.uniform(1 - self._deviation, 1 - self._deviation / 2)
                )
                self.data.update(next_target=None)
                raise SkipIteration  # skip call to _next()

            except BrokenBarrierError:
                self.barrier.reset()
                return self._rebuff()
                # raise SkipIteration
        else:
            # Count the number of times we've been blocked in last minute.
            # If > 5, then we're unable to cast unless we move. # TODO - move
            if (
                len([i for i in self._blocked_at_logs if time.perf_counter() - i < 60])
                > 5
            ):
                self._blocked_at_logs.clear()
                raise RuntimeError(
                    f"{self} has rebuffed more than 5 times in last minute. Exiting."
                )

    def _confirm_rebuffed(self) -> bool:
        left, top, right, bottom = win32gui.GetClientRect(self.data.handle)
        buff_icon_box = Box(left=right - 350, top=top + 45, right=right, bottom=85)
        haystack = buff_icon_box.extract_client_img(self.data.current_client_img)
        for idx, icon in enumerate(self._buff_icons):
            results = cv2.matchTemplate(haystack, icon, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, _, max_loc = cv2.minMaxLoc(results)
            if max_val > 0.95:
                # Double check by extracting icon to gray and count bright pixels
                rect = max_loc + (icon.shape[1], icon.shape[0])
                rect_img = haystack[
                    rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]
                ]
                gray = cv2.cvtColor(rect_img, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                bright_pixels = cv2.countNonZero(thresh)
                if bright_pixels > 350:
                    continue
            return False
        logger.debug(f"{self} has confirmed all rebuffs.")
        return True

    def _exception_handler(self, e: Exception) -> None:
        if isinstance(e, SkipIteration):
            # Occurs when failsafe is successful
            self._error_counter -= 1
            return
        if self._error_counter > 3:
            # If failsafe fails 3 times, raise the exception
            raise e

    def _rebuff(self) -> QueueAction:
        # Decrement the ready counter, and re-increment when rebuffing action completes
        self.block_generators("Rotation", id(self))
        self.blocked = True
        return QueueAction(
            identifier=f"{self}",
            priority=1,
            action=partial(
                self.cast_all,
                self.data.casting_until,
                self.data.handle,
                self.data.ign,
                self.buffs,
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={
                    "blocked": False,
                    "unblock_generators": ("Rotation", id(self)),
                },
            ),
        )

    @staticmethod
    async def cast_all(
        ready_at: float, handle: int, ign: str, skills: list[RoyalsSkill], *args
    ):
        for skill in skills:
            await cast_skill(handle, ign, skill, ready_at)
