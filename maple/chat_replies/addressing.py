"""
Whether a chat line is meant for the character: it must be answered, the model
judges it, or it is ignored.

- `MUST`: a whisper to us, any party or buddy line (they only reach our party
  and buddies), and a general line whose message names the IGN as a whole word,
  in any case. Names are compared as read (`maple.screen.chat.reads_as`): an
  `l` read as `I`, or an unread letter, still names us, and a word with too few
  letters read never does.
- `GM`: a line of kind `gm`, and any later line from a speaker seen as a GM.
  Those speakers are the only state `Addressing` keeps, for the session.
- `JUDGE`: any other general line from someone else. The model decides whether
  it was meant for us, and may stay silent. It passes through `judge_gate`
  first, where how close the speaker is (D9), or how many players are on the
  map, plugs in later.
- `IGNORE`: our own lines, a general line `judge_gate` rejects, and the kinds
  never answered (megaphone, system, `unknown`).

A row that `continues` the line above asks nothing on its own: it is `MUST`
when its text names the IGN, `IGNORE` otherwise. `Conversation` joins it to the
line above, which keeps the stronger of the two addresses.
"""

import enum
from collections.abc import Iterable
from dataclasses import dataclass

from maple.screen.chat import ChatKind, reads_as
from maple.screen.font import UNREAD

from .line import ReadLine, same_name, same_speaker


class Address(enum.Enum):
    GM = "gm"
    MUST = "must"
    JUDGE = "judge"
    IGNORE = "ignore"


STRENGTH: dict[Address, int] = {
    Address.GM: 3,
    Address.MUST: 2,
    Address.JUDGE: 1,
    Address.IGNORE: 0,
}
"""How strongly an address asks for a reply: a burst of lines takes the
strongest of its lines'."""


def strongest(addresses: Iterable[Address]) -> Address:
    """The strongest of `addresses`, by `STRENGTH`."""
    return max(addresses, key=STRENGTH.__getitem__)


_ALWAYS_ANSWERED = frozenset({ChatKind.WHISPER, ChatKind.PARTY, ChatKind.BUDDY})


@dataclass(frozen=True, slots=True)
class Evidence:
    """
    What is known about a general line beyond its text, for `judge_gate`.
    Nothing yet: how close its speaker is (D9) and how many players are on the
    map are added here when they can be read.
    """


NO_EVIDENCE = Evidence()


def judge_gate(line: ReadLine, evidence: Evidence) -> bool:
    """
    Whether a general line not naming us goes to the model to judge. A line it
    rejects is `IGNORE`. Every line passes, for now.
    """
    return True


class Addressing:
    """Classifies the lines of one character's chat. One per bot session."""

    def __init__(self, ign: str) -> None:
        self.ign = ign
        self._gms: list[str] = []

    def classify(self, line: ReadLine, evidence: Evidence = NO_EVIDENCE) -> Address:
        """The line's address. A line of kind `gm` is remembered: its speaker's
        later lines are `GM` too, whatever their kind."""
        if line.continues:
            return Address.MUST if self.names_us(line.text) else Address.IGNORE
        if line.outgoing or same_name(line.speaker, self.ign):
            return Address.IGNORE
        if line.kind is ChatKind.GM:
            speaker = line.speaker
            if speaker is not None and not any(
                same_speaker(speaker, gm) for gm in self._gms
            ):
                self._gms.append(speaker)
            return Address.GM
        if line.kind not in _ALWAYS_ANSWERED and line.kind is not ChatKind.GENERAL:
            return Address.IGNORE
        if line.speaker is not None and any(
            same_speaker(line.speaker, gm) for gm in self._gms
        ):
            return Address.GM
        if line.kind in _ALWAYS_ANSWERED:
            return Address.MUST
        if self.names_us(line.message):
            return Address.MUST
        return Address.JUDGE if judge_gate(line, evidence) else Address.IGNORE

    def names_us(self, text: str | None) -> bool:
        """
        Whether `text`, as read, names the IGN as a whole word, in any case
        (`reads_as`). A word ends at the text's ends, or at a character read
        that can't be part of a word. An `UNREAD` character may be part of one,
        so it ends none: in `Bob?`, its `?` unread, `Bob` isn't named.
        """
        if text is None:
            return False
        n = len(self.ign)
        for start in range(len(text) - n + 1):
            end = start + n
            if (
                (start == 0 or not _in_word(text[start - 1]))
                and (end == len(text) or not _in_word(text[end]))
                and reads_as(text[start:end], self.ign, ignore_case=True)
            ):
                return True
        return False


def _in_word(c: str) -> bool:
    """Whether `c`, as read, may be part of a word: a letter, a digit, `_`, or
    a character not read."""
    return c.isalnum() or c == "_" or c == UNREAD
