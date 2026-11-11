import multiprocessing.managers
import random
from collections.abc import Callable
from typing import ClassVar

from botting.core import ActionRequest, BotData, DiscordRequest
from botting.utilities import cooldown
from maple.actions import chat_keys, priorities, write_in_chat


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

    def _draw(self, reaction_type: str, choices: list[str]) -> str:
        """
        Draws a line without replacement from this instance's own shuffled copy of
        `choices`, and reshuffles a fresh copy once it is used up. The class-level
        list is never modified, and a refill never starts with the line just sent.
        """
        decks: dict[str, list[str]] = self.__dict__.setdefault("_reaction_decks", {})
        last: dict[str, str] = self.__dict__.setdefault("_reaction_last", {})
        deck = decks.get(reaction_type)
        if not deck:
            deck = random.sample(choices, len(choices))
            if len(deck) > 1 and deck[-1] == last.get(reaction_type):
                # Lines are drawn from the end, so swap the repeat out of it.
                deck[0], deck[-1] = deck[-1], deck[0]
            decks[reaction_type] = deck
        selected = deck.pop()
        last[reaction_type] = selected
        return selected

    @cooldown(10)
    def _react(self, reaction_type: str, disc_msg: str | None = None) -> None:
        """
        Reacts to a certain event by sending a message to the chat.
        """
        if reaction_type == "light":
            disc_alert = (
                None
                if disc_msg is None
                else DiscordRequest(disc_msg, self.data.current_frame.pixels)
            )
            choices = self._light_reactions
        else:
            disc_alert = DiscordRequest(
                disc_msg or f"{self} is failing", self.data.current_frame.pixels
            )
            choices = self._advanced_reactions

        selected = self._draw(reaction_type, choices)
        self.send(
            ActionRequest(
                f"{self} - Writing to chat",
                write_in_chat,
                self.data.ign,
                priorities.ANTI_DETECTION,
                block_lower_priority=True,
                args=(self.data.handle, selected),
                kwargs={"keys": chat_keys(self.data.ign)},
                discord_request=disc_alert,
            )
        )
