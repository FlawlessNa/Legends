import random
import time
from abc import ABC, abstractmethod
from functools import partial

from botting.core import QueueAction
from royals.actions import random_chat_response


class AntiDetectionReactions(ABC):
    """
    Manages reactions triggered by an Anti-Detection generator.
    There is a cooldown between reactions, and a maximum number of reactions.
    """

    def __init__(self, cooldown: int, max_reactions: int) -> None:
        self.cooldown = cooldown
        self.max_reactions = max_reactions
        self._last_txt_choice = None
        self._reaction_counter = 0
        self._last_trigger = 0

    @property
    @abstractmethod
    def reaction_choices(self) -> list:
        pass

    def _reaction(self, handle: int, messages: list) -> QueueAction | None:
        """
        Triggers emergency reaction, which is three-fold:
        1. Block bot from continuing until user calls RESUME from discord.
            Note: If no RESUME within 60 seconds, the bot stops.
        2. Random reaction in general chat
        3. Send Discord Alert
        :return:
        """
        if time.perf_counter() - self._last_trigger < self.cooldown:
            return

        self._reaction_counter += 1
        self._last_trigger = time.perf_counter()

        all_choices = self.reaction_choices.copy()
        if self._last_txt_choice in all_choices:
            all_choices.remove(self._last_txt_choice)
        self._last_txt_choice = random.choice(all_choices)
        func = partial(
            random_chat_response,
            handle=handle,
            msg=self._last_txt_choice,
        )
        return QueueAction(
            f"{self.__class__.__name__} reaction",
            priority=1,
            action=func,
            user_message=messages
        )

