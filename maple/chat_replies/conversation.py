"""
The session's chat as one conversation: every line read, in order, which ones
are ours, and which are left to answer.

**Entries.** Each line the chat reader reports is appended once, with its
`Address`, as an `Entry` numbered by the conversation's own counter (`seq`).
Megaphone, system and `unknown` lines are never appended: they are no one's
words to answer or to quote.

**Ours.** An entry is ours when the reader says the line is outgoing, or its
speaker is the IGN. A misread IGN would make the character answer itself, so a
reply the relay sent is also registered with `expect_echo`: the first line on
that channel whose message matches it within `ECHO_WINDOW` seconds is ours too,
whatever speaker was read. Our entries are never `pending`.

**State.** `MUST`, `GM` and `JUDGE` entries start `pending`; `IGNORE` entries,
ours, and every entry appended while replies are off start `context`: kept,
and never answered, not even once replies are on again. A pending entry leaves
`pending` exactly once, through `resolve`, to `answered`, `silent` or `failed`.

**Bursts.** `pending` groups what is left to answer by player and channel: one
reply answers everything one player said on one channel since our last answer
to them.
"""

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from maple.screen.chat import ChatKind

from .addressing import Address, strongest
from .line import ReadLine, same_name

ECHO_WINDOW = 10.0
"""Seconds after `expect_echo` within which our reply's echo is recognised."""
UNREAD = "�"
"""What the chat reader reads for a character it has no glyph for. It matches
any character when an echo is compared with what was sent."""
APPENDED_KINDS = frozenset(
    {ChatKind.GENERAL, ChatKind.PARTY, ChatKind.BUDDY, ChatKind.WHISPER, ChatKind.GM}
)


class EntryState(enum.Enum):
    CONTEXT = "context"
    """Kept as context for the model, never answered."""
    PENDING = "pending"
    ANSWERED = "answered"
    SILENT = "silent"
    """The model chose not to answer."""
    FAILED = "failed"


RESOLVED = frozenset({EntryState.ANSWERED, EntryState.SILENT, EntryState.FAILED})


@dataclass(frozen=True, slots=True)
class Entry:
    """
    One line of the conversation.

    :ivar seq: Its place in the conversation, from 1.
    :ivar kind: The line's kind, which is also its channel.
    :ivar speaker: Who wrote it, as read; `None` when the reader couldn't split it.
    :ivar message: What they wrote, as read; `None` likewise.
    :ivar ours: The character wrote it.
    :ivar seen_at: When it was appended, on the conversation's clock.
    :ivar state: Where it is in being answered.
    :ivar address: What `Addressing` made of the line, which its burst's
        address is taken from.
    """

    seq: int
    kind: ChatKind
    speaker: str | None
    message: str | None
    ours: bool
    seen_at: float
    state: EntryState
    address: Address


@dataclass(frozen=True, slots=True)
class Burst:
    """
    Everything one player said on one channel that is left to answer, oldest
    first. One reply answers it.

    :ivar address: The strongest of its entries' (`GM`, then `MUST`, then `JUDGE`).
    """

    speaker: str | None
    channel: ChatKind
    address: Address
    entries: tuple[Entry, ...]


@dataclass(frozen=True, slots=True)
class _Echo:
    text: str
    channel: ChatKind
    expected_at: float


class Conversation:
    """
    One character's chat for the session. Kept whole in memory; `recent` is the
    part a request to the model carries.
    """

    def __init__(
        self, ign: str, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ign = ign
        self._clock = clock
        self._entries: list[Entry] = []
        self._echoes: list[_Echo] = []

    def append(
        self, line: ReadLine, address: Address, *, replies_on: bool = True
    ) -> Entry | None:
        """
        Append a line the chat reader reported, once, with its address. `None`,
        and nothing appended, for a megaphone, system or `unknown` line.

        :param replies_on: Whether automatic replies are on. A line appended
            while they are off is `context`, and is never answered late.
        """
        if line.kind not in APPENDED_KINDS:
            return None
        now = self._clock()
        # The echo is taken even from a line known to be ours, so it can't be
        # matched later by another player's line repeating it.
        echoed = self._take_echo(line, now)
        ours = line.outgoing or same_name(line.speaker, self.ign) or echoed
        answerable = address is not Address.IGNORE and not ours and replies_on
        entry = Entry(
            seq=len(self._entries) + 1,
            kind=line.kind,
            speaker=line.speaker,
            message=line.message,
            ours=ours,
            seen_at=now,
            state=EntryState.PENDING if answerable else EntryState.CONTEXT,
            address=address,
        )
        self._entries.append(entry)
        return entry

    def pending(self) -> list[Burst]:
        """What is left to answer: one burst per player and channel, oldest first."""
        groups: dict[tuple[str | None, ChatKind], list[Entry]] = {}
        for entry in self._entries:
            if entry.state is EntryState.PENDING:
                groups.setdefault((entry.speaker, entry.kind), []).append(entry)
        return [
            Burst(
                speaker=speaker,
                channel=channel,
                address=strongest([e.address for e in entries]),
                entries=tuple(entries),
            )
            for (speaker, channel), entries in groups.items()
        ]

    def resolve(self, burst: Burst, state: EntryState) -> None:
        """
        Move every entry of `burst` out of `pending`, to `state`. Lines that
        arrived since `burst` was taken stay pending.

        :raises ValueError: `state` isn't `answered`, `silent` or `failed`, or an
            entry of the burst already left `pending`. Nothing is changed then.
        """
        if state not in RESOLVED:
            raise ValueError(
                f"an entry leaves pending to {state.value}: not a resolution"
            )
        for entry in burst.entries:
            current = self._entries[entry.seq - 1]
            if current.state is not EntryState.PENDING:
                raise ValueError(
                    f"entry {entry.seq} already left pending ({current.state.value})"
                )
        for entry in burst.entries:
            self._entries[entry.seq - 1] = replace(
                self._entries[entry.seq - 1], state=state
            )

    def expect_echo(self, text: str, channel: ChatKind) -> None:
        """Register a reply sent on `channel`, so the line that echoes it is ours
        even if its speaker misreads."""
        self._echoes.append(_Echo(text.strip(), channel, self._clock()))

    def recent(self, n: int = 50) -> list[Entry]:
        """The last `n` entries, oldest first: what a request to the model carries."""
        return self._entries[-n:] if n > 0 else []

    def _take_echo(self, line: ReadLine, now: float) -> bool:
        """Whether `line` echoes a reply we sent, consuming that reply if so."""
        self._echoes = [e for e in self._echoes if now - e.expected_at <= ECHO_WINDOW]
        if line.message is None:
            return False
        for echo in self._echoes:
            if echo.channel is line.kind and _echoes(line.message, echo.text):
                self._echoes.remove(echo)
                return True
        return False


def _echoes(read: str, sent: str) -> bool:
    """Whether a message as read is the one sent: the same length once stripped,
    and equal character by character, an unread character matching any."""
    read = read.strip()
    return len(read) == len(sent) and all(
        r == s or r == UNREAD for r, s in zip(read, sent, strict=True)
    )
