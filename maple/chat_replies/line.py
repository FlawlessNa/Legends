"""
What the reply side reads from a chat line.

`maple.screen.chat.ChatLine` has these fields: the kind from its colours, the
speaker, message and direction split from its text by the kind's format, and
whether the row continues the line above. Splitting is the reader's job, so
nothing here parses `text`.

Whether a name read is a given one goes through `maple.screen.chat.reads_as`,
like every other "does this read as that": `same_name` and `same_speaker`.
"""

from typing import Protocol

from maple.screen.chat import ChatKind, reads_as


class ReadLine(Protocol):
    """
    A line the chat reader reported, as `Addressing` and `Conversation` read it.

    :ivar kind: What kind of line it is, from its colours.
    :ivar speaker: Who wrote it, when the kind's format gives it; `None` when it
        couldn't be split.
    :ivar message: What they wrote, without the speaker; `None` likewise.
    :ivar outgoing: The character sent it: an outgoing whisper's own format, or
        `speaker` equal to the IGN.
    :ivar text: Everything the row reads, for the kinds whose text is read;
        `None` for the others.
    :ivar continues: The row is the rest of the line above, which wrapped: it
        has no speaker, and its words are in `text` only.
    """

    @property
    def kind(self) -> ChatKind: ...

    @property
    def speaker(self) -> str | None: ...

    @property
    def message(self) -> str | None: ...

    @property
    def outgoing(self) -> bool: ...

    @property
    def text(self) -> str | None: ...

    @property
    def continues(self) -> bool: ...


def same_name(speaker: str | None, name: str) -> bool:
    """Whether `speaker`, as read, may be `name`, the IGN or another name known
    whole: `reads_as`, ignoring case, since in-game names are unique whatever
    their case. A speaker with too few letters read is no one's name."""
    return speaker is not None and reads_as(speaker, name, ignore_case=True)


def same_speaker(a: str | None, b: str | None) -> bool:
    """
    Whether two speakers, both as read, may be the same player: either reads as
    the other (`same_name`), so `Bob` and `bob` are, and so are `Bob` and `B?b`
    with its `?` unread. Two lines with no speaker are the same unknown speaker,
    and one with a speaker never is.
    """
    if a is None or b is None:
        return a is b
    return same_name(a, b) or same_name(b, a)
