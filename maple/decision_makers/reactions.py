"""
Chat lines the character types when something is off, the way a player would.
"""

import itertools
import random
from typing import ClassVar, Protocol

from botting.core import HANDLE, ActionRequest, BotData, DiscordRequest, Key
from botting.utilities import cooldown
from maple.actions import priorities, write_in_chat

from .providers import CHAT_KEYS, FRAME

_REACTIONS = itertools.count(1)
"""Numbers each reaction's request. A reaction may wait behind a reply being typed
(`writing`'s chat-input guard) for longer than its cooldown, so the next can come
while it is still running, and two requests sharing an identifier end the Task
Manager."""


class _Owner(Protocol):
    """Who reacts: names the request, and sends it."""

    data: BotData

    def send(self, request: ActionRequest) -> None: ...


class _Reader(Protocol):
    def read[T](self, key: Key[T]) -> T: ...


class Reactions:
    """
    Semi-random reactions to an event: a short line in the chat, with a Discord
    alert and the client's image for an `"advanced"` one, or for a `"light"`
    one given a Discord message.

    A DecisionMaker holds one, and declares `reads` in its own. Every holder in
    the process shares one 10 s cooldown, as `ReactionsMixin._react` always
    has: a reaction within 10 s of another, whoever sent it, is dropped.
    """

    #: The keys it reads, which its holder declares.
    reads = (FRAME, HANDLE, CHAT_KEYS)

    LIGHT: ClassVar[list[str]] = [
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
    ADVANCED: ClassVar[list[str]] = [
        "Whaaaat is up?",
        "What the actual ? is going on",
        "Why????",
        "Can I help you??",
        "What's up?",
        "Uhm Hello?",
    ]

    def __init__(self, owner: _Owner, reader: _Reader) -> None:
        """
        :param owner: Who reacts: the requests carry its name, and go through its
            `send`.
        :param reader: What `reads` is read through: the owner itself when it
            declares them, or the Bot's `BotData` for an unported owner.
        """
        self.owner = owner
        self.reader = reader
        #: Each reaction type's shuffled lines still to send, and the last sent.
        self._decks: dict[str, list[str]] = {}
        self._last: dict[str, str] = {}

    @cooldown(10)
    def react(self, reaction_type: str, disc_msg: str | None = None) -> None:
        """
        Types a line of `reaction_type` in the chat, `"light"` or `"advanced"`.
        :param disc_msg: The Discord alert's message: a light reaction sends an
            alert only with one; an advanced one always does.
        """
        if reaction_type == "light":
            disc_alert = (
                None
                if disc_msg is None
                else DiscordRequest(disc_msg, self.reader.read(FRAME).pixels)
            )
            choices = type(self).LIGHT
        else:
            disc_alert = DiscordRequest(
                disc_msg or f"{self.owner} is failing", self.reader.read(FRAME).pixels
            )
            choices = type(self).ADVANCED

        selected = self._draw(reaction_type, choices)
        self.owner.send(
            ActionRequest(
                f"{self.owner} - Writing to chat #{next(_REACTIONS)}",
                write_in_chat,
                self.owner.data.ign,
                priorities.ANTI_DETECTION,
                block_lower_priority=True,
                args=(self.reader.read(HANDLE), selected),
                kwargs={"keys": self.reader.read(CHAT_KEYS)},
                discord_request=disc_alert,
            )
        )

    def _draw(self, reaction_type: str, choices: list[str]) -> str:
        """
        Draws a line without replacement from this holder's own shuffled copy of
        `choices`, and reshuffles a fresh copy once it is used up. The class-level
        list is never modified, and a refill never starts with the line just sent.
        """
        deck = self._decks.get(reaction_type)
        if not deck:
            deck = random.sample(choices, len(choices))
            if len(deck) > 1 and deck[-1] == self._last.get(reaction_type):
                # Lines are drawn from the end, so swap the repeat out of it.
                deck[0], deck[-1] = deck[-1], deck[0]
            self._decks[reaction_type] = deck
        selected = deck.pop()
        self._last[reaction_type] = selected
        return selected
