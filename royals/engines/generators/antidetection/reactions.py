from abc import ABC, abstractmethod
from functools import partial

from botting.core import QueueAction
from royals.actions import random_chat_response


class AntiDetectionReactions(ABC):
    def __init__(self) -> None:
        self._last_txt_choice = None

    @property
    @abstractmethod
    def reaction_choices(self) -> list:
        pass

    def _reaction(self, handle: int, messages: list) -> QueueAction:
        """
        Triggers emergency reaction, which is three-fold:
        1. Block bot from continuing until user calls RESUME from discord.
            Note: If no RESUME within 60 seconds, the bot stops.
        2. Random reaction in general chat
        3. Send Discord Alert
        :return:
        """
        all_choices = self.reaction_choices.copy()
        if self._last_txt_choice in all_choices:
            all_choices.remove(self._last_txt_choice)
        func = partial(
            random_chat_response,
            handle=handle,
            choices=all_choices,
        )
        return QueueAction(
            f"{self.__class__.__name__} reaction",
            priority=1,
            action=func,
            user_message=[messages]
        )

