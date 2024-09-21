import random
import multiprocessing.connection
import multiprocessing.managers

from botting import controller
from botting.core import ActionRequest, BotData, DiscordRequest
from botting.utilities import cooldown
from royals.actions import write_in_chat, priorities


class ReactionsMixin:
    """
    Mixin class that can be used to generate semi-random reactions to certain events.
    """
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection

    _light_reactions = [
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
    _advanced_reactions = [
        "Whaaaat is up?",
        "What the actual ? is going on",
        "Why????",
        "Can I help you??",
        "What's up?",
        "Uhm Hello?",
    ]

    @cooldown(10)
    def _react(self, reaction_type: str, disc_msg: str = None) -> None:
        """
        Reacts to a certain event by sending a message to the chat.
        """
        if reaction_type == "light":
            disc_alert = None if disc_msg is None else DiscordRequest(
                disc_msg,
                self.data.current_client_img
            )
            choices = self._light_reactions
        else:
            disc_alert = DiscordRequest(
                disc_msg or f"{self} is failing",
                self.data.current_client_img
            )
            choices = self._advanced_reactions

        selected = random.choice(choices)
        choices.remove(selected)
        self.pipe.send(
            ActionRequest(
                f"{self} - Writing to chat",
                write_in_chat,
                self.data.ign,
                priorities.ANTI_DETECTION,
                block_lower_priority=True,
                args=(self.data.handle, selected),
                discord_request=disc_alert
            )
        )
        controller.release_keys(['left', 'right', 'up', 'down'], self.data.handle)
