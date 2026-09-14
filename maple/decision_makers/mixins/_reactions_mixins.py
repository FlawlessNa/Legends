import multiprocessing.managers
import random
from collections.abc import Callable
from typing import ClassVar

from botting.core import ActionRequest, BotData, DiscordRequest
from botting.utilities import cooldown
from maple.actions import priorities, write_in_chat


class ReactionsMixin:
    """
    Mixin class that can be used to generate semi-random reactions to certain events.
    """

    data: BotData
    metadata: multiprocessing.managers.DictProxy
    send: Callable[[ActionRequest], None]

    _light_reactions: ClassVar[list[str]] = [
        "wtf",
        "wassup?",
        "why?",
        "why",
        "?",
        "???",
        "tha hell",
        "wth",
        "wth?",
        "wtf!",
        "wtf!?",
    ]
    _advanced_reactions: ClassVar[list[str]] = [
        "Whaaaat is up?",
        "What the actual ? is going on",
        "Why????",
        "Can I help you??",
        "What's up?",
        "Uhm Hello?",
    ]

    @cooldown(10)
    def _react(self, reaction_type: str, disc_msg: str | None = None) -> None:
        """
        Reacts to a certain event by sending a message to the chat.
        """
        if reaction_type == "light":
            disc_alert = (
                None
                if disc_msg is None
                else DiscordRequest(disc_msg, self.data.current_client_img)
            )
            choices = self._light_reactions
        else:
            disc_alert = DiscordRequest(
                disc_msg or f"{self} is failing", self.data.current_client_img
            )
            choices = self._advanced_reactions

        selected = random.choice(choices)
        choices.remove(selected)
        self.send(
            ActionRequest(
                f"{self} - Writing to chat",
                write_in_chat,
                self.data.ign,
                priorities.ANTI_DETECTION,
                block_lower_priority=True,
                args=(self.data.handle, selected),
                discord_request=disc_alert,
            )
        )
