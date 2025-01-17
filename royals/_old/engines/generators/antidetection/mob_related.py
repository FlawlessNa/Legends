import logging
import time

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionGenerator
from royals._old.engines.generators.interval_based import IntervalBasedGenerator
from royals._old.engines.generators.antidetection.reactions import (
    AntiDetectionReactions,
)
from royals._old.game_data import AntiDetectionData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MobCheck(IntervalBasedGenerator, AntiDetectionReactions):
    """
    Generator for checking if mobs are on screen.
    Emergency action is taken if mobs are not detected for a certain amount of time.
    There is a double check failsafe with a 1 sec delay to confirm there are indeed no
    mobs detected.
    When triggered, a random reaction is sent to general chat.
    After a small cooldown, a second reaction is sent if there are still no mobs.
    The bot is on hold indefinitely until the user sends RESUME from discord.
    """

    generator_type = "AntiDetection"

    def __init__(
        self,
        data: AntiDetectionData,
        time_threshold: int,
        mob_threshold: int,
        cooldown: int = 15,
        max_reactions: int = 2,
    ) -> None:
        super().__init__(data, interval=1, deviation=0)
        super(DecisionGenerator, self).__init__(cooldown, max_reactions)

        self.time_threshold = time_threshold
        self.mob_threshold = mob_threshold

        self._fail_counter = 0
        self._last_detection = time.perf_counter()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    @DecisionGenerator.blocked.setter
    def blocked(self, value) -> None:
        """
        When this generator is unblocked, reset relevant data.
        :param value:
        """
        super(MobCheck, MobCheck).blocked.fset(self, value)
        if not value:
            self._last_detection = time.perf_counter()
            self._fail_counter = 0
            self._reaction_counter = 0

    @property
    def initial_data_requirements(self) -> tuple:
        return tuple()

    def _update_continuous_data(self) -> None:
        pass

    def _next(self) -> QueueAction | None:
        nbr_mobs = 0
        mobs = self.data.current_mobs
        for mob in mobs:
            img = mob.detection_box.extract_client_img(self.data.current_client_img)
            nbr_mobs += mob.get_mob_count(img, debug=False)

        if nbr_mobs >= self.mob_threshold:
            if self._reaction_counter == 1:
                self._reaction_counter = 0
                self.unblock_generators("Rotation", id(self))
            self._last_detection = time.perf_counter()
            self._fail_counter = 0

        elif time.perf_counter() - self._last_detection > self.time_threshold:
            self._fail_counter += 1
            self._next_call = time.perf_counter() + self.interval

        if self._fail_counter >= 2:
            self.block_generators("Rotation", id(self))
            msg = f"""
            No detection in last {time.perf_counter() - self._last_detection} seconds.
            Send Resume to continue.
            """
            reaction = self._reaction(
                self.data.handle, [msg, self.data.current_client_img]
            )
            if reaction is not None:
                logger.warning(
                    f"Rotation Blocked. Sending random reaction to chat due to {self}."
                )
            return reaction

    def _failsafe(self):
        """
        TODO - Read chat to ensure that the bot properly reacted.
        :return:
        """
        if self._reaction_counter >= self.max_reactions:
            self.blocked = True
            return

    @property
    def reaction_choices(self) -> dict:
        return {
            1: [
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
            ],
            2: [
                "Hello?",
                "What's going on?",
                "Can I help you?",
                "What's up?",
                "Anyone here?",
                "Hi??",
                "Hello??",
                "Whats happening",
                "Uh wth is going on",
            ],
        }

    def _exception_handler(self, e: Exception) -> None:
        raise e
