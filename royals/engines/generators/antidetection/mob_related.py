import logging
import random
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, controller, QueueAction
from botting.utilities import take_screenshot
from royals import RoyalsData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MobCheck(DecisionGenerator):
    """
    Generator for checking if mobs are on screen.
    Emergency action is taken if mobs are not detected for a certain amount of time.
    """

    def __init__(
        self, data: RoyalsData, time_threshold: int = 10, mob_threshold: int = 3
    ) -> None:
        self.data = data
        self.time_threshold = time_threshold
        self.mob_threshold = mob_threshold

    def __call__(self):
        self._last_mob_detection = time.perf_counter()
        self._counter = 0
        self._img = None
        return iter(self)

    def __next__(self) -> QueueAction | None:
        if self._counter >= 2:
            return self._failsafe()

        self._img = take_screenshot(self.data.handle)
        nbr_mobs = 0
        mobs = self.data.current_mobs
        for mob in mobs:
            nbr_mobs += mob.get_mob_count(self._img, debug=False)

        if nbr_mobs >= self.mob_threshold:
            self._last_mob_detection = time.perf_counter()
            self._counter = 0

        elif time.perf_counter() - self._last_mob_detection > self.time_threshold:
            self._counter += 1

    def _failsafe(self) -> QueueAction:
        """
        Triggers emergency reaction, which is three-fold:
        1. Block bot from continuing until user calls RESUME from discord.  # TODO
            Note: If no RESUME within 60 seconds, the bot stops.  # TODO (but within Executor, not here)
        2. Random reaction in general chat
        3. Send Discord Alert
        :return:
        """
        self._counter = 0
        reaction_text = random.choice(
            [
                "wtf",
                "wut",
                "wtf?",
                "hmmm?",
                "?",
                "???",
                "uh",
                "huh",
                "tha hell",
                "wth",
                "wth?",
                "wtf!",
                "wtf!?",
            ]
        )
        logger.warning(
            f"No mobs detected for {self.time_threshold} seconds. Writing {reaction_text}."
        )

        func = partial(controller.write, handle=self.data.handle, message=reaction_text)
        return QueueAction(
            f"{self.__class__.__name__} reaction",
            priority=1,
            action=func,
            user_message=[f"No mobs detected for {self.time_threshold} seconds.", self._img],
        )
