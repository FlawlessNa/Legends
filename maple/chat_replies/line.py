"""
What the reply side reads from a chat line.

`maple.screen.chat.ChatLine` has these fields once #456 lands: the kind from
its colours, and the speaker, message and direction split from its text by the
kind's format. Splitting is the reader's job, so nothing here parses `text`.
"""

from typing import Protocol

from maple.screen.chat import ChatKind


class ReadLine(Protocol):
    """
    A line the chat reader reported, as `Addressing` and `Conversation` read it.

    :ivar kind: What kind of line it is, from its colours.
    :ivar speaker: Who wrote it, when the kind's format gives it; `None` when it
        couldn't be split.
    :ivar message: What they wrote, without the speaker; `None` likewise.
    :ivar outgoing: The character sent it: an outgoing whisper's own format, or
        `speaker` equal to the IGN.
    """

    @property
    def kind(self) -> ChatKind: ...

    @property
    def speaker(self) -> str | None: ...

    @property
    def message(self) -> str | None: ...

    @property
    def outgoing(self) -> bool: ...


def same_name(speaker: str | None, ign: str) -> bool:
    """Whether `speaker` is the character's IGN. In-game names are unique
    whatever their case."""
    return speaker is not None and speaker.casefold() == ign.casefold()
