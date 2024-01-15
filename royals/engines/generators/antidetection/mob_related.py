import logging
import random
import time

from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction
from royals.actions import write_in_chat
from royals.game_data import AntiDetectionData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MobCheck(DecisionGenerator):
    """
    Generator for checking if mobs are on screen.
    Emergency action is taken if mobs are not detected for a certain amount of time.
    """
    generator_type = "AntiDetection"

    def __init__(
        self,
        data: AntiDetectionData,
        time_threshold: int,
        mob_threshold: int,
        cooldown: int = 60,
    ) -> None:

        super().__init__(data)
        self.time_threshold = time_threshold
        self.mob_threshold = mob_threshold
        self.cooldown = cooldown
        self._counter = 0
        self._last_trigger = 0

    @property
    def data_requirements(self) -> tuple:
        return (
            "latest_client_img",
            "mob_check_last_detection",
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    def _next(self) -> QueueAction | None:
        if self.data.shut_down_at is not None and time.perf_counter() > self.data.shut_down_at:
            logger.critical(f"Shutting down due to {self.__class__.__name__}")
            raise RuntimeError(f"Shutting down due to {self.__class__.__name__}")

        if (
            self._counter >= 2
            and time.perf_counter() - self._last_trigger > self.cooldown
        ):
            return self._reaction()

        self.data.update("latest_client_img")
        nbr_mobs = 0
        mobs = self.data.current_mobs
        for mob in mobs:
            nbr_mobs += mob.get_mob_count(self.data.latest_client_img.copy(), debug=False)

        if nbr_mobs >= self.mob_threshold:
            self.data.update("mob_check_last_detection")
            self._counter = 0

        elif time.perf_counter() - self.data.mob_check_last_detection > self.time_threshold:
            self._counter += 1

    def _failsafe(self):
        """
        Todo - Read chat to ensure that the bot properly reacted.
        :return:
        """

    def _reaction(self) -> QueueAction:
        """
        Triggers emergency reaction, which is three-fold:
        1. Block bot from continuing until user calls RESUME from discord.
            Note: If no RESUME within 60 seconds, the bot stops.
        2. Random reaction in general chat
        3. Send Discord Alert
        :return:
        """
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

        func = partial(
            write_in_chat,
            handle=self.data.handle,
            message=reaction_text,
            channel="general",
        )
        self._last_trigger = time.perf_counter()
        self._counter = 0
        self.data.update(
            shut_down_at=self._last_trigger + self.cooldown
        )
        self.data.block("Rotation")
        return QueueAction(
            f"{self.__class__.__name__} reaction",
            priority=1,
            action=func,
            user_message=[
                f"""
                No mobs detected for {self.time_threshold} seconds. Shutting Down in {self.cooldown} seconds.
                Send Resume to continue.
                Send Hold to pause indefinitely.
                """,
                self.data.latest_client_img,
            ],
        )
