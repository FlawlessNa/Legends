import logging
import time

from botting import PARENT_LOG
from botting.core import QueueAction
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.engines.generators.antidetection.reactions import AntiDetectionReactions
from royals.game_data import AntiDetectionData

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
    ) -> None:

        super().__init__(data, interval=1, deviation=0)
        self.time_threshold = time_threshold
        self.mob_threshold = mob_threshold
        self.cooldown = cooldown

        self._fail_counter = 0
        self._reaction_counter = 0
        self._last_trigger = 0
        self._last_detection = time.perf_counter()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    @property
    def initial_data_requirements(self) -> tuple:
        return tuple()

    def _update_continuous_data(self) -> None:
        pass

    def _next(self) -> QueueAction | None:
        nbr_mobs = 0
        mobs = self.data.current_mobs
        for mob in mobs:
            nbr_mobs += mob.get_mob_count(self.data.current_client_img.copy(),
                                          debug=False)

        if nbr_mobs >= self.mob_threshold:
            self._last_detection = time.perf_counter()
            self._fail_counter = 0
            self._reaction_counter = 0
            self.data.unblock("Rotation")

        elif time.perf_counter() - self._last_detection > self.time_threshold:
            self._fail_counter += 1
            self._next_call = time.perf_counter() + self.interval

        if (
            self._fail_counter >= 2
            and time.perf_counter() - self._last_trigger > self.cooldown
        ):
            if self._reaction_counter >= 2:
                self.blocked = True
                return

            self._reaction_counter += 1
            self._last_trigger = time.perf_counter()
            self.data.block("Rotation")
            logger.warning(
                f"Rotation Blocked. Sending random reaction to chat."
            )
            msg = f"""
            No detection in last {time.perf_counter() - self._last_detection} seconds.
            Send Resume to continue.
            """
            return self._reaction(self.data.handle,
                                  [msg, self.data.current_client_img])

    def _failsafe(self):
        """
        TODO - Read chat to ensure that the bot properly reacted.
        :return:
        """
        pass

    @property
    def reaction_choices(self) -> list:
        return [
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

    def _exception_handler(self, e: Exception) -> None:
        raise e
