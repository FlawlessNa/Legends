"""
The session's chat as one conversation: every line read, in order, which ones
are ours, and which are left to answer.

**Entries.** Each line the chat reader reports is appended once, with its
`Address`, as an `Entry` numbered by the conversation's own counter (`seq`).
Megaphone, system and `unknown` lines are never appended: they are no one's
words to answer or to quote.

**Ours.** An entry is ours when the reader says the line is outgoing, or its
speaker reads as the IGN (`same_name`). A misread IGN would make the character
answer itself, so a reply the relay sent is also registered with `expect_echo`:
the first line on that channel whose message reads as it
(`maple.screen.chat.reads_as`, with its minimum of letters read) within
`ECHO_WINDOW` seconds is ours too, whatever speaker was read. Our entries are
never `pending`.

**Wrapped lines.** A row that `continues` the line above (the reader's word for
the rest of a line that wrapped) is not an entry of its own: it is joined to the
last entry, the line above, when that is of the same kind. Its text is added to
that entry's message after a space, the entry takes the stronger of the two
addresses (`Addressing` makes the row `MUST` when it names the IGN), and the
whole message is matched against our echoes again, since a reply that wraps
only reads whole once joined. A row that continues nothing is appended as it
is: a line with no speaker.

**State.** `MUST`, `GM` and `JUDGE` entries start `pending`; `IGNORE` entries,
ours, and every entry appended while replies are off start `context`: kept,
and never answered, not even once replies are on again. A pending entry leaves
`pending` exactly once, through `resolve`, to `answered`, `silent` or `failed`.
The one exception is a line whose next row shows it was our echo: it was ours
all along, so the join makes it `context`. Both rows arrive in the same read,
so this happens before the caller asks what is `pending`.

**Bursts.** `pending` groups what is left to answer by player and channel: one
reply answers everything one player said on one channel since our last answer
to them. A player is told by `same_speaker`, so `Bob` and `bob` are one.
"""

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from maple.screen import font
from maple.screen.chat import ChatKind, reads_as

from .addressing import Address, strongest
from .line import ReadLine, same_name, same_speaker

ECHO_WINDOW = 10.0
"""Seconds after `expect_echo` within which our reply's echo is recognised."""
UNREAD = font.UNREAD
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

        A row that `continues` the line above is joined to the last entry
        instead (module docstring), and that entry, updated, is returned: the
        same `seq`, not a new entry.

        :param replies_on: Whether automatic replies are on. A line appended
            while they are off is `context`, and is never answered late.
        """
        if line.kind not in APPENDED_KINDS:
            return None
        now = self._clock()
        if line.continues and self._entries and self._entries[-1].kind is line.kind:
            return self._join(line, address, now, replies_on=replies_on)
        # The echo is taken even from a line known to be ours, so it can't be
        # matched later by another player's line repeating it.
        echoed = self._take_echo(line.message, line.kind, now)
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

    def _join(
        self, line: ReadLine, address: Address, now: float, *, replies_on: bool
    ) -> Entry:
        """Join a row that continues the line above to the last entry."""
        last = self._entries[-1]
        rest = (line.text or "").strip()
        message = last.message
        if message is not None and rest:
            message = f"{message} {rest}"
        echoed = message != last.message and self._take_echo(message, line.kind, now)
        ours = last.ours or echoed
        joined = last.address if ours else strongest([last.address, address])
        state = last.state
        if ours:
            if state is EntryState.PENDING:
                state = EntryState.CONTEXT
        elif (
            state is EntryState.CONTEXT
            and last.address is Address.IGNORE
            and joined is not Address.IGNORE
            and replies_on
        ):
            # Ignored on its first row, it names us on the next.
            state = EntryState.PENDING
        entry = replace(last, message=message, ours=ours, state=state, address=joined)
        self._entries[-1] = entry
        return entry

    def pending(self) -> list[Burst]:
        """What is left to answer: one burst per player and channel, oldest first.
        A player is told by `same_speaker`, against the first entry of a burst."""
        groups: list[list[Entry]] = []
        for entry in self._entries:
            if entry.state is not EntryState.PENDING:
                continue
            for group in groups:
                if group[0].kind is entry.kind and same_speaker(
                    group[0].speaker, entry.speaker
                ):
                    group.append(entry)
                    break
            else:
                groups.append([entry])
        return [
            Burst(
                speaker=_best_read(entries),
                channel=entries[0].kind,
                address=strongest([e.address for e in entries]),
                entries=tuple(entries),
            )
            for entries in groups
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

    def _take_echo(self, message: str | None, channel: ChatKind, now: float) -> bool:
        """Whether a line on `channel` saying `message` echoes a reply we sent,
        consuming that reply if so."""
        self._echoes = [e for e in self._echoes if now - e.expected_at <= ECHO_WINDOW]
        if message is None:
            return False
        for echo in self._echoes:
            if echo.channel is channel and _echoes(message, echo.text):
                self._echoes.remove(echo)
                return True
        return False


def _echoes(read: str, sent: str) -> bool:
    """Whether a message as read is the one sent: once both are stripped, it
    reads as it (`reads_as`, case kept), so an unread character matches any,
    an `I` matches an `l`, and a message with too few letters read matches
    nothing."""
    return reads_as(read.strip(), sent)


def _best_read(entries: list[Entry]) -> str | None:
    """The speaker of a burst: the one of its entries' with the most letters
    read, the earliest of those. A whisper goes to that name."""
    return max(
        (e.speaker for e in entries),
        key=lambda s: 0 if s is None else len(s) - s.count(UNREAD),
    )
